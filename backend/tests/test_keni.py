"""Keni sync: connecting, and mirroring money received as income in a Keni wallet.

Requests go to a fake Keni that answers like the real API, never the real one. The clock is
pinned to 23 October 2026, 10:00 in Asia/Taipei."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import keni, keni_sync
from app.clock import get_now
from app.config import settings
from app.main import app
from app.models import AppSettings, KeniLink

NOW = datetime(2026, 10, 23, 2, 0, tzinfo=UTC)
URL = "https://keni.example.com"
TOKEN = "keni-token-that-must-stay-secret"
WALLET = "6f1c1d2e-0000-4000-8000-000000000001"
CATEGORY = "0b9a4c3d-0000-4000-8000-000000000002"


class FakeKeni:
    """The parts of Keni's API the dashboard uses, with one user's wallets, categories and
    transactions."""

    def __init__(self) -> None:
        self.wallets = {
            WALLET: {"id": WALLET, "name": "Studio", "currency": "TWD"},
            "other": {"id": "other", "name": "Travel", "currency": "JPY"},
        }
        self.categories = {
            CATEGORY: {"id": CATEGORY, "name": "Freelance"},
            "salary": {"id": "salary", "name": "Salary"},
        }
        self.transactions: dict[str, dict] = {}
        self.calls: list[tuple[str, str]] = []
        self.down = False

    def __call__(self, method: str, url: str, token: str, json: object = None) -> httpx.Response:
        self.calls.append((method, url))
        if self.down:
            raise httpx.ConnectError("Connection refused")
        if token != TOKEN:
            return httpx.Response(401, json={"detail": "Invalid credentials"})
        assert url.startswith(f"{URL}/api/")
        match method, url.removeprefix(f"{URL}/api/").split("/"):
            case "GET", ["categories"]:
                return httpx.Response(200, json=list(self.categories.values()))
            case "GET", ["wallets"]:
                return httpx.Response(200, json=list(self.wallets.values()))
            case "GET", ["wallets", wallet]:
                if wallet not in self.wallets:
                    return httpx.Response(404, json={"detail": "Wallet not found"})
                return httpx.Response(200, json=self.wallets[wallet])
            case _, ["wallets", wallet, "transactions", *rest]:
                if wallet not in self.wallets:
                    return httpx.Response(404, json={"detail": "Wallet not found"})
                return self._transaction(method, wallet, rest, json)
        raise AssertionError(f"unexpected {method} {url}")

    def _transaction(self, method: str, wallet: str, rest: list[str], body) -> httpx.Response:
        if method == "POST" and not rest:
            if body["category_id"] not in self.categories:
                return httpx.Response(404, json={"detail": "Category not found"})
            transaction_id = str(uuid.uuid4())
            self.transactions[transaction_id] = {**body, "wallet_id": wallet}
            return httpx.Response(201, json={"id": transaction_id, **body})
        [transaction_id] = rest
        if transaction_id not in self.transactions:
            return httpx.Response(404, json={"detail": "Transaction not found"})
        if method == "PATCH":
            self.transactions[transaction_id] |= body
            return httpx.Response(200, json={"id": transaction_id})
        assert method == "DELETE"
        del self.transactions[transaction_id]
        return httpx.Response(204)

    @property
    def recorded(self) -> list[tuple[int, str, str]]:
        """(amount, date, description) of each transaction, by date."""
        rows = [(t["amount"], t["date"], t["description"]) for t in self.transactions.values()]
        return sorted(rows, key=lambda row: (row[1], row[2]))


@pytest.fixture(autouse=True)
def _pinned() -> Iterator[None]:
    app.dependency_overrides[get_now] = lambda: NOW
    yield
    app.dependency_overrides.pop(get_now, None)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeKeni:
    """Swaps in the fake Keni, with ENCRYPTION_KEY set so a token can be saved."""
    fake = FakeKeni()
    monkeypatch.setattr(keni, "_request", fake)
    monkeypatch.setattr(settings, "encryption_key", SecretStr("k" * 32))
    return fake


def connect(client: TestClient, wallet: str = WALLET, category: str = CATEGORY) -> dict:
    body = {"url": f"{URL}/", "token": TOKEN, "wallet_id": wallet, "category_id": category}
    response = client.put("/api/settings/keni", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def choose(client: TestClient, wallet: str, category: str):
    return client.put(
        "/api/settings/keni/destination", json={"wallet_id": wallet, "category_id": category}
    )


def status(client: TestClient) -> dict:
    response = client.get("/api/settings/keni")
    assert response.status_code == 200, response.text
    return response.json()


def sync(session: Session, now: datetime = NOW) -> int:
    return keni_sync.sync(session, now)


def make_project(client: TestClient, name: str = "Northwind Coffee") -> dict:
    owner = client.post("/api/clients", json={"name": name}).json()
    response = client.post(
        "/api/projects",
        json={
            "client_id": owner["id"],
            "name": "Online ordering site",
            "price": 48000,
            "started_on": "2026-09-01",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def pay(client: TestClient, project_id: int, amount: int, **fields: object) -> dict:
    body = {"amount": amount, "paid_on": "2026-10-20"} | fields
    response = client.post(f"/api/projects/{project_id}/payments", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def make_retainer(client: TestClient, **fields: object) -> dict:
    owner = client.post("/api/clients", json={"name": "Lumen Yoga"}).json()
    body = {
        "client_id": owner["id"],
        "amount": 2500,
        "due_day": 5,
        "collection": "auto_transfer",
        "started_on": "2026-01-01",
        **fields,
    }
    response = client.post("/api/retainers", json=body)
    assert response.status_code == 201, response.text
    return response.json()


# Connecting


def test_not_connected_by_default(client: TestClient, session: Session) -> None:
    assert status(client) == {
        "url": None,
        "wallet_id": None,
        "wallet_name": None,
        "wallet_currency": None,
        "category_id": None,
        "category_name": None,
        "connected_on": None,
        "pending": 0,
        "error": None,
    }
    assert sync(session) == 0  # and nothing reaches Keni (see conftest)


OPTIONS = {
    "wallets": [
        {"id": WALLET, "name": "Studio", "currency": "TWD"},
        {"id": "other", "name": "Travel", "currency": "JPY"},
    ],
    "categories": [{"id": CATEGORY, "name": "Freelance"}, {"id": "salary", "name": "Salary"}],
}


def test_lists_wallets_and_categories_for_a_token(client: TestClient, fake: FakeKeni) -> None:
    response = client.post("/api/settings/keni/options", json={"url": URL, "token": TOKEN})
    assert response.status_code == 200, response.text
    assert response.json() == OPTIONS
    assert fake.calls == [("GET", f"{URL}/api/wallets"), ("GET", f"{URL}/api/categories")]


def test_wrong_token_or_unreachable_keni_is_a_bad_gateway(
    client: TestClient, fake: FakeKeni
) -> None:
    response = client.post("/api/settings/keni/options", json={"url": URL, "token": "nope"})
    assert response.status_code == 502
    assert response.json()["detail"] == "Keni didn't accept the API key"

    fake.down = True
    response = client.post("/api/settings/keni/options", json={"url": URL, "token": TOKEN})
    assert response.status_code == 502
    assert response.json()["detail"] == "Couldn't reach Keni: Connection refused"


def test_url_must_be_http(client: TestClient) -> None:
    response = client.post("/api/settings/keni/options", json={"url": "keni", "token": TOKEN})
    assert response.status_code == 422


def test_connect_stores_the_token_encrypted(
    client: TestClient, session: Session, fake: FakeKeni
) -> None:
    assert connect(client) == {
        "url": URL,
        "wallet_id": WALLET,
        "wallet_name": "Studio",
        "wallet_currency": "TWD",
        "category_id": CATEGORY,
        "category_name": "Freelance",
        "connected_on": "2026-10-23",
        "pending": 0,
        "error": None,
    }
    row = session.get_one(AppSettings, 1)
    assert row.keni_wallet_id == WALLET
    assert row.keni_token_encrypted is not None
    assert TOKEN not in row.keni_token_encrypted
    assert TOKEN not in client.get("/api/settings/keni").text


@pytest.mark.parametrize(
    ("wallet", "category", "detail"),
    [
        ("missing", CATEGORY, "That wallet isn't in your Keni account"),
        (WALLET, "missing", "That category isn't in your Keni account"),
    ],
)
def test_connect_checks_the_wallet_and_category(
    client: TestClient, fake: FakeKeni, wallet: str, category: str, detail: str
) -> None:
    body = {"url": URL, "token": TOKEN, "wallet_id": wallet, "category_id": category}
    response = client.put("/api/settings/keni", json=body)
    assert response.status_code == 502
    assert response.json()["detail"] == detail
    assert status(client)["url"] is None


def test_connect_needs_an_encryption_key(client: TestClient) -> None:
    body = {"url": URL, "token": TOKEN, "wallet_id": WALLET, "category_id": CATEGORY}
    response = client.put("/api/settings/keni", json=body)
    assert response.status_code == 409
    assert "ENCRYPTION_KEY" in response.json()["detail"]


def test_disconnect_stops_syncing(client: TestClient, session: Session, fake: FakeKeni) -> None:
    connect(client)
    project = make_project(client)
    pay(client, project["id"], 24000)
    sync(session)

    response = client.delete("/api/settings/keni")
    assert response.status_code == 200
    assert response.json()["url"] is None
    assert session.scalars(select(KeniLink)).all() == []
    pay(client, project["id"], 1000)
    assert sync(session) == 0
    assert len(fake.transactions) == 1  # what was sent stays in Keni


# Choosing where income goes


def test_options_use_the_saved_token(client: TestClient, fake: FakeKeni) -> None:
    assert client.get("/api/settings/keni/options").status_code == 409  # not connected
    connect(client)
    response = client.get("/api/settings/keni/options")
    assert response.status_code == 200, response.text
    assert response.json() == OPTIONS


def test_changing_wallet_and_category_applies_to_new_income(
    client: TestClient, session: Session, fake: FakeKeni
) -> None:
    connect(client)
    project = make_project(client)
    first = pay(client, project["id"], 24000)
    sync(session)

    response = choose(client, "other", "salary")
    assert response.status_code == 200, response.text
    out = response.json()
    assert (out["wallet_name"], out["wallet_currency"], out["category_name"]) == (
        "Travel",
        "JPY",
        "Salary",
    )
    pay(client, project["id"], 4000)
    sync(session)
    placed = sorted(
        (t["amount"], t["wallet_id"], t["category_id"]) for t in fake.transactions.values()
    )
    assert placed == [(4000, "other", "salary"), (24000, WALLET, CATEGORY)]

    # Edits and deletes still reach the first payment in the wallet it went to.
    client.put(
        f"/api/projects/{project['id']}/payments/{first['id']}",
        json={"amount": 20000, "paid_on": "2026-10-20", "note": None},
    ).raise_for_status()
    assert sync(session) == 1
    assert sorted(t["amount"] for t in fake.transactions.values()) == [4000, 20000]
    client.delete(f"/api/projects/{project['id']}/payments/{first['id']}").raise_for_status()
    assert sync(session) == 1
    assert [t["wallet_id"] for t in fake.transactions.values()] == ["other"]


def test_changing_needs_a_connection_and_real_choices(
    client: TestClient, fake: FakeKeni
) -> None:
    assert choose(client, WALLET, CATEGORY).status_code == 409
    connect(client)
    response = choose(client, WALLET, "missing")
    assert response.status_code == 502
    assert response.json()["detail"] == "That category isn't in your Keni account"
    assert status(client)["category_id"] == CATEGORY


def test_category_deleted_in_keni_stops_sync(
    client: TestClient, session: Session, fake: FakeKeni
) -> None:
    connect(client)
    project = make_project(client)
    pay(client, project["id"], 24000)
    del fake.categories[CATEGORY]
    with pytest.raises(keni.Error):
        sync(session)
    assert status(client)["error"] == "Keni refused the request: Category not found"


# Mirroring payments


def test_payments_recorded_before_connecting_stay_out(
    client: TestClient, session: Session, fake: FakeKeni
) -> None:
    project = make_project(client)
    pay(client, project["id"], 24000)
    connect(client)
    assert status(client)["pending"] == 0
    assert sync(session) == 0
    assert fake.transactions == {}


def test_new_payment_is_recorded_as_income(
    client: TestClient, session: Session, fake: FakeKeni
) -> None:
    connect(client)
    project = make_project(client)
    pay(client, project["id"], 24000, note="Bank transfer")
    assert status(client)["pending"] == 1

    assert sync(session) == 1
    [transaction] = fake.transactions.values()
    assert transaction == {
        "type": "income",
        "category_id": CATEGORY,
        "amount": 24000,
        "date": "2026-10-20T00:00:00+08:00",
        "description": "Northwind Coffee · Online ordering site (Bank transfer)",
        "wallet_id": WALLET,
    }
    assert status(client)["pending"] == 0
    assert sync(session) == 0  # nothing more to send


def test_addition_payment_names_the_addition(
    client: TestClient, session: Session, fake: FakeKeni
) -> None:
    connect(client)
    project = make_project(client)
    addition = client.post(
        f"/api/projects/{project['id']}/additions",
        json={"name": "Giveaway feature", "price": 500, "agreed_on": "2026-10-01"},
    ).json()
    pay(client, project["id"], 500, addition_id=addition["id"])
    sync(session)
    assert fake.recorded == [
        (
            500,
            "2026-10-20T00:00:00+08:00",
            "Northwind Coffee · Online ordering site · Giveaway feature",
        )
    ]


def test_edits_and_deletes_are_mirrored(
    client: TestClient, session: Session, fake: FakeKeni
) -> None:
    connect(client)
    project = make_project(client)
    payment = pay(client, project["id"], 24000)
    sync(session)

    client.put(
        f"/api/projects/{project['id']}/payments/{payment['id']}",
        json={"amount": 20000, "paid_on": "2026-10-21", "note": None},
    ).raise_for_status()
    assert sync(session) == 1
    assert fake.recorded == [
        (20000, "2026-10-21T00:00:00+08:00", "Northwind Coffee · Online ordering site")
    ]

    client.delete(f"/api/projects/{project['id']}/payments/{payment['id']}").raise_for_status()
    assert sync(session) == 1
    assert fake.transactions == {}
    assert session.scalars(select(KeniLink)).all() == []


def test_renaming_a_client_updates_the_description(
    client: TestClient, session: Session, fake: FakeKeni
) -> None:
    connect(client)
    project = make_project(client)
    pay(client, project["id"], 24000)
    sync(session)
    response = client.put(
        f"/api/clients/{project['client']['id']}", json={"name": "Northwind Roasters"}
    )
    assert response.status_code == 200, response.text
    assert sync(session) == 1
    assert fake.recorded[0][2] == "Northwind Roasters · Online ordering site"


def test_deleting_a_project_deletes_its_payments_in_keni(
    client: TestClient, session: Session, fake: FakeKeni
) -> None:
    connect(client)
    project = make_project(client)
    pay(client, project["id"], 24000)
    pay(client, project["id"], 4000)
    sync(session)
    assert len(fake.transactions) == 2

    client.delete(f"/api/projects/{project['id']}").raise_for_status()
    assert sync(session) == 2
    assert fake.transactions == {}


def test_editing_a_payment_from_before_connecting_still_stays_out(
    client: TestClient, session: Session, fake: FakeKeni
) -> None:
    project = make_project(client)
    payment = pay(client, project["id"], 24000)
    connect(client)
    client.put(
        f"/api/projects/{project['id']}/payments/{payment['id']}",
        json={"amount": 20000, "paid_on": "2026-10-20", "note": None},
    ).raise_for_status()
    client.delete(f"/api/projects/{project['id']}/payments/{payment['id']}").raise_for_status()
    assert sync(session) == 0
    # Just the connect checks.
    assert fake.calls == [("GET", f"{URL}/api/wallets/{WALLET}"), ("GET", f"{URL}/api/categories")]
    assert session.scalars(select(KeniLink)).all() == []


def test_transaction_deleted_in_keni_is_kept_out(
    client: TestClient, session: Session, fake: FakeKeni
) -> None:
    connect(client)
    project = make_project(client)
    payment = pay(client, project["id"], 24000)
    sync(session)
    fake.transactions.clear()

    client.put(
        f"/api/projects/{project['id']}/payments/{payment['id']}",
        json={"amount": 20000, "paid_on": "2026-10-20", "note": None},
    ).raise_for_status()
    assert sync(session) == 1
    assert fake.transactions == {}  # not created again
    assert sync(session) == 0


# Maintenance


def test_ask_retainer_payments_are_mirrored(
    client: TestClient, session: Session, fake: FakeKeni
) -> None:
    connect(client)
    retainer = make_retainer(client, collection="ask", started_on="2026-10-01")
    response = client.post(
        f"/api/retainers/{retainer['id']}/payments",
        json={"period": "2026-10-01", "amount": 2500, "paid_on": "2026-10-06"},
    )
    assert response.status_code == 201, response.text
    sync(session)
    assert fake.recorded == [
        (2500, "2026-10-06T00:00:00+08:00", "Lumen Yoga · Maintenance")
    ]

    payment_id = response.json()["id"]
    client.delete(f"/api/retainers/{retainer['id']}/payments/{payment_id}").raise_for_status()
    sync(session)
    assert fake.transactions == {}


def test_months_paid_ahead_are_one_transaction(
    client: TestClient, session: Session, fake: FakeKeni
) -> None:
    connect(client)
    retainer = make_retainer(client, collection="ask", started_on="2026-10-01")
    response = client.post(
        f"/api/retainers/{retainer['id']}/payments",
        json={"period": "2026-11-01", "months": 3, "amount": 7500, "paid_on": "2026-10-20"},
    )
    assert response.status_code == 201, response.text
    sync(session)
    assert fake.recorded == [
        (7500, "2026-10-20T00:00:00+08:00", "Lumen Yoga · Maintenance (Nov 2026–Jan 2027)")
    ]


def test_auto_transfers_count_once_due_after_connecting(
    client: TestClient, session: Session, fake: FakeKeni
) -> None:
    retainer = make_retainer(client)  # due on the 5th since January
    connect(client)  # 23 October: up to October has been received already
    assert sync(session) == 0

    assert sync(session, datetime(2026, 11, 4, 16, 0, tzinfo=UTC)) == 1  # 5 Nov 00:00 local
    assert fake.recorded == [
        (2500, "2026-11-05T00:00:00+08:00", "Lumen Yoga · Maintenance")
    ]

    # A new amount applies to every month the dashboard counts, so Keni follows.
    client.put(
        f"/api/retainers/{retainer['id']}",
        json={
            "client_id": retainer["client"]["id"],
            "amount": 3000,
            "due_day": 5,
            "collection": "auto_transfer",
            "ask_via_id": None,
            "started_on": "2026-01-01",
            "ended_on": None,
            "tracked_from": "2026-01-01",
        },
    ).raise_for_status()
    assert sync(session, datetime(2026, 12, 5, 2, 0, tzinfo=UTC)) == 2
    assert [amount for amount, *_ in fake.recorded] == [3000, 3000]

    client.delete(f"/api/retainers/{retainer['id']}").raise_for_status()
    assert sync(session, datetime(2026, 12, 5, 2, 0, tzinfo=UTC)) == 2
    assert fake.transactions == {}


# Failures


def test_failure_is_shown_and_retried(
    client: TestClient, session: Session, fake: FakeKeni
) -> None:
    connect(client)
    project = make_project(client)
    pay(client, project["id"], 24000)
    fake.down = True

    with pytest.raises(keni.Error):
        sync(session)
    assert status(client) == {
        "url": URL,
        "wallet_id": WALLET,
        "wallet_name": "Studio",
        "wallet_currency": "TWD",
        "category_id": CATEGORY,
        "category_name": "Freelance",
        "connected_on": "2026-10-23",
        "pending": 1,
        "error": "Couldn't reach Keni: Connection refused",
    }

    fake.down = False
    assert sync(session) == 1
    assert len(fake.transactions) == 1
    assert status(client)["error"] is None
    assert status(client)["pending"] == 0


def test_tick_survives_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """The loop's next tick retries, so a failure is logged, not raised."""

    def fail(*args: object) -> int:
        raise keni.Error("Keni didn't accept the API key")

    monkeypatch.setattr(keni_sync, "sync", fail)
    keni_sync.tick()


def test_unreadable_token_stops_sync(
    client: TestClient, session: Session, fake: FakeKeni, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect(client)
    monkeypatch.setattr(settings, "encryption_key", SecretStr("a different key" * 3))
    with pytest.raises(keni.Error):
        sync(session)
    assert "ENCRYPTION_KEY" in status(client)["error"]
