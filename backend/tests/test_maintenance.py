"""Retainers, monthly status, the Maintenance overview, Settings and Discord reminders.

The clock is pinned: "now" is Friday 23 October 2026, 10:00 in Asia/Taipei (the default
timezone) unless a test moves it. Reminders post through a recorder, never to Discord."""

from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crypto, discord, maintenance, reminders
from app.clock import get_now
from app.config import settings
from app.main import app
from app.maintenance import Month, MonthStatus, due_on
from app.models import (
    AppSettings,
    Collection,
    ContactKind,
    ContactMethod,
    ReminderLog,
    Retainer,
    RetainerPayment,
)

TAIPEI = ZoneInfo("Asia/Taipei")
TOKYO = ZoneInfo("Asia/Tokyo")
REAL_POST = discord.post  # before conftest swaps it out
USER_ID = "123456789012345678"
KEY = "k" * 32  # ENCRYPTION_KEY, for the webhook URL
TODAY = date(2026, 10, 23)


def at(day: str | date, hour: int = 10, minute: int = 0, tz: ZoneInfo = TAIPEI) -> datetime:
    day = date.fromisoformat(day) if isinstance(day, str) else day
    return datetime.combine(day, time(hour, minute), tz)


@pytest.fixture(autouse=True)
def pin() -> Iterator[Callable[[datetime], None]]:
    """Pins the API's clock; call it to move to another moment."""

    def move(moment: datetime) -> None:
        app.dependency_overrides[get_now] = lambda: moment

    move(at(TODAY))
    yield move
    app.dependency_overrides.pop(get_now, None)


@pytest.fixture
def webhook(session: Session, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Turns reminders on in Settings and records each message instead of posting it."""
    sent: list[str] = []
    monkeypatch.setattr(settings, "encryption_key", SecretStr(KEY))
    row = session.get_one(AppSettings, 1)
    row.discord_webhook_url = "https://discord.com/api/webhooks/1/x"
    row.discord_mention_user_id = int(USER_ID)
    session.flush()
    discord.load(session)
    monkeypatch.setattr(discord, "post", sent.append)
    return sent


def make_client(
    client: TestClient, name: str = "Northwind Coffee", contacts: tuple = (("discord", "@danpark"),)
) -> dict:
    created = client.post("/api/clients", json={"name": name})
    assert created.status_code == 201, created.text
    for kind, value in contacts:
        response = client.post(
            f"/api/clients/{created.json()['id']}/contacts", json={"kind": kind, "value": value}
        )
        assert response.status_code == 201, response.text
    return client.get(f"/api/clients/{created.json()['id']}").json()


def make_retainer(client: TestClient, owner: dict, **fields: object) -> dict:
    body = {
        "client_id": owner["id"],
        "amount": 250,
        "due_day": 25,
        "collection": "ask",
        "ask_via_id": owner["contacts"][0]["id"] if owner["contacts"] else None,
        "started_on": "2026-10-01",
        **fields,
    }
    if body["collection"] == "auto_transfer":
        body["ask_via_id"] = fields.get("ask_via_id")
    response = client.post("/api/retainers", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def put_retainer(client: TestClient, retainer: dict, **changes: object):
    fields = ("client_id", "project_id", "amount", "due_day", "collection", "ask_via_id")
    body = {k: retainer[k] for k in (*fields, "started_on", "ended_on", "tracked_from")} | changes
    return client.put(f"/api/retainers/{retainer['id']}", json=body)


def pay(client: TestClient, retainer_id: int, period: str, **fields: object):
    body = {"period": period, "amount": 250, "paid_on": str(TODAY), **fields}
    return client.post(f"/api/retainers/{retainer_id}/payments", json=body)


def get(client: TestClient, retainer_id: int) -> dict:
    response = client.get(f"/api/retainers/{retainer_id}")
    assert response.status_code == 200, response.text
    return response.json()


def overview(client: TestClient, **params: str) -> dict:
    response = client.get("/api/maintenance", params=params)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def owner(client: TestClient) -> dict:
    return make_client(client)


def transient(**fields: object) -> Retainer:
    """A retainer that never touches the database, for the pure date logic."""
    payments = fields.pop("payments", [])
    started_on = fields.get("started_on", date(2026, 1, 1))
    retainer = Retainer(
        **{
            "client_id": 1,
            "amount": 250,
            "due_day": 25,
            "collection": Collection.ASK,
            "started_on": started_on,
            "ended_on": None,
            "tracked_from": started_on.replace(day=1),
        }
        | fields
    )
    retainer.payments = payments
    return retainer


# Due dates and month status


@pytest.mark.parametrize(
    ("period", "due_day", "expected"),
    [
        ("2026-02-01", 31, "2026-02-28"),
        ("2028-02-01", 31, "2028-02-29"),  # leap year
        ("2026-02-01", 29, "2026-02-28"),
        ("2026-02-01", 28, "2026-02-28"),
        ("2026-04-01", 31, "2026-04-30"),
        ("2026-04-01", 30, "2026-04-30"),
        ("2026-01-01", 31, "2026-01-31"),
        ("2026-10-01", 1, "2026-10-01"),
    ],
)
def test_due_date_clamps_to_month_end(period: str, due_day: int, expected: str) -> None:
    assert due_on(date.fromisoformat(period), due_day) == date.fromisoformat(expected)


def test_clamped_due_dates_in_the_api(client: TestClient, owner: dict, pin) -> None:
    retainer = make_retainer(client, owner, due_day=31, started_on="2026-01-01")
    months = {m["period"]: m["due_on"] for m in retainer["overdue"]}
    assert months["2026-02-01"] == "2026-02-28"
    assert months["2026-04-01"] == "2026-04-30"
    assert months["2026-09-01"] == "2026-09-30"
    assert retainer["next_due_on"] == "2026-10-31"

    pin(at("2027-02-27"))
    calendar = overview(client, month="2027-02")["calendar"]
    assert [d["day"] for d in calendar] == ["2027-02-28"]
    assert calendar[0]["status"] == "upcoming"
    pin(at("2027-03-02"))  # two days after the clamped due date: still in its grace days
    assert overview(client, month="2027-02")["calendar"][0]["status"] == "due"
    pin(at("2027-03-03"))
    assert overview(client, month="2027-02")["calendar"][0]["status"] == "overdue"


@pytest.mark.parametrize(
    ("today", "auto", "ask", "days", "late"),
    [
        ("2026-10-24", "upcoming", "upcoming", 0, False),
        ("2026-10-25", "paid", "due", 0, False),  # due today: auto counts as paid
        ("2026-10-27", "paid", "due", 2, False),  # day 2: still within the grace days
        ("2026-10-28", "paid", "overdue", 3, True),  # day 3: overdue
    ],
)
def test_auto_vs_ask_status_and_grace(
    today: str, auto: str, ask: str, days: int, late: bool
) -> None:
    period, day = date(2026, 10, 1), date.fromisoformat(today)
    auto_month = maintenance.month(transient(collection=Collection.AUTO_TRANSFER), period, day)
    ask_month = maintenance.month(transient(), period, day)
    assert (auto_month.status, ask_month.status) == (auto, ask)
    assert (ask_month.days_late, ask_month.late) == (days, late)
    if auto == "paid":
        assert auto_month.paid_on == date(2026, 10, 25)
        assert auto_month.late is False
    assert ask_month.paid_on is None


@pytest.mark.parametrize(("paid_on", "days", "late"), [("27", 2, False), ("28", 3, True)])
def test_payment_is_late_only_after_the_grace_days(paid_on: str, days: int, late: bool) -> None:
    payment = RetainerPayment(
        id=7, period=date(2026, 10, 1), months=1, amount=200, paid_on=date(2026, 10, int(paid_on))
    )
    october = maintenance.month(transient(payments=[payment]), date(2026, 10, 1), TODAY)
    assert october.status == MonthStatus.PAID
    assert (october.amount, october.payment) == (200, payment)
    assert (october.days_late, october.late) == (days, late)


def test_ask_is_paid_only_with_a_recorded_payment() -> None:
    payment = RetainerPayment(
        id=7, period=date(2026, 10, 1), months=1, amount=200, paid_on=date(2026, 10, 20)
    )
    retainer = transient(payments=[payment])
    # Paying ahead counts too.
    assert maintenance.month(retainer, date(2026, 10, 1), date(2026, 10, 2)).status == "paid"
    october = maintenance.month(retainer, date(2026, 10, 1), date(2026, 10, 30))
    assert (october.days_late, october.late) == (0, False)
    november = maintenance.month(retainer, date(2026, 11, 1), date(2026, 11, 30))
    assert (november.status, november.days_late) == (MonthStatus.OVERDUE, 5)


def test_status_through_the_api(client: TestClient, owner: dict, pin) -> None:
    ask = make_retainer(client, owner)
    auto = make_retainer(client, owner, collection="auto_transfer", amount=180, due_day=1)
    assert ask["this_month"]["status"] == "upcoming"
    assert ask["this_month"]["due_on"] == "2026-10-25"
    assert auto["this_month"] == {
        "period": "2026-10-01",
        "due_on": "2026-10-01",
        "amount": 180,
        "status": "paid",
        "paid_on": "2026-10-01",
        "payment": None,
        "days_late": 0,
        "late": False,
    }
    pin(at("2026-10-26"))
    ask = get(client, ask["id"])
    assert ask["this_month"]["status"] == "due"
    assert ask["overdue"] == []
    pin(at("2026-10-28"))
    ask = get(client, ask["id"])
    assert ask["this_month"]["status"] == "overdue"
    assert (ask["this_month"]["days_late"], ask["this_month"]["late"]) == (3, True)

    # Recording the payment flips it to paid.
    payment = pay(client, ask["id"], "2026-10-01", paid_on="2026-10-27").json()
    assert payment["period"] == "2026-10-01"
    ask = get(client, ask["id"])
    assert ask["this_month"]["status"] == "paid"
    assert (ask["this_month"]["days_late"], ask["this_month"]["late"]) == (2, False)
    assert ask["this_month"]["payment"] == payment
    assert ask["overdue"] == []
    assert ask["received"] == 250


def test_multiple_overdue_months(client: TestClient, owner: dict) -> None:
    retainer = make_retainer(client, owner, due_day=10, started_on="2026-07-01")
    overdue = retainer["overdue"]
    assert [m["period"] for m in overdue] == [
        "2026-07-01",
        "2026-08-01",
        "2026-09-01",
        "2026-10-01",
    ]
    assert [m["days_late"] for m in overdue] == [105, 74, 43, 13]

    pay(client, retainer["id"], "2026-08-15")  # any day in the month names the month
    retainer = get(client, retainer["id"])
    assert [m["period"] for m in retainer["overdue"]] == ["2026-07-01", "2026-09-01", "2026-10-01"]
    assert retainer["received"] == 250

    data = overview(client)
    assert [(o["period"], o["days"]) for o in data["overdue"]] == [
        ("2026-07-01", 105),
        ("2026-09-01", 43),
        ("2026-10-01", 13),
    ]
    assert data["overdue"][0]["client"] == {
        "id": owner["id"],
        "name": "Northwind Coffee",
        "avatar_url": None,
    }


@pytest.mark.parametrize(
    ("started_on", "ended_on", "billed"),
    [
        ("2026-10-25", None, True),  # starts on the due date
        ("2026-10-26", None, False),  # starts after it: first billed in November
        ("2026-09-01", "2026-10-25", True),  # ends on the due date
        ("2026-09-01", "2026-10-24", False),  # ends the day before
    ],
)
def test_start_and_end_boundaries(started_on: str, ended_on: str | None, billed: bool) -> None:
    retainer = transient(
        started_on=date.fromisoformat(started_on),
        ended_on=date.fromisoformat(ended_on) if ended_on else None,
    )
    assert maintenance.is_billed(retainer, date(2026, 10, 1)) is billed


def test_boundaries_through_the_api(client: TestClient, owner: dict) -> None:
    late_start = make_retainer(client, owner, started_on="2026-10-26")
    assert late_start["this_month"] is None
    assert late_start["active"] is False
    assert late_start["next_due_on"] == "2026-11-25"
    assert late_start["overdue"] == []

    ended = make_retainer(client, owner, due_day=5, started_on="2026-08-01", ended_on="2026-09-04")
    # August is billed; September's due date (5th) is after the end.
    assert [m["period"] for m in ended["months"]] == ["2026-08-01"]
    assert [m["period"] for m in ended["overdue"]] == ["2026-08-01"]
    assert ended["active"] is False
    assert ended["this_month"] is None
    assert ended["next_due_on"] is None
    # Unpaid months stay owed after the retainer ends.
    assert pay(client, ended["id"], "2026-09-01").status_code == 409
    assert pay(client, ended["id"], "2026-08-01").status_code == 201

    data = overview(client)
    assert (data["active_count"], data["monthly_total"]) == (0, 0)
    assert [r["id"] for r in data["retainers"]] == sorted([late_start["id"], ended["id"]])


def test_recent_months_end_with_the_next_one_due(client: TestClient, owner: dict, pin) -> None:
    retainer = make_retainer(client, owner, started_on="2026-01-01")
    months = retainer["months"]
    assert [m["period"][:7] for m in months] == [
        "2026-05",
        "2026-06",
        "2026-07",
        "2026-08",
        "2026-09",
        "2026-10",
    ]
    assert months[-1]["status"] == "upcoming"
    # Once October's due date passes, November is the next one.
    pin(at("2026-10-26"))
    months = get(client, retainer["id"])["months"]
    assert [m["period"][:7] for m in months][-2:] == ["2026-10", "2026-11"]
    assert [m["status"] for m in months][-2:] == ["due", "upcoming"]


def test_received_counts_auto_transfers_by_due_date(client: TestClient, owner: dict) -> None:
    auto = make_retainer(
        client, owner, collection="auto_transfer", amount=300, due_day=10, started_on="2026-08-10"
    )
    assert auto["received"] == 900  # 10 Aug, 10 Sep, 10 Oct
    assert auto["overdue"] == []


# Retainer CRUD and payments


def test_create_get_update_delete(client: TestClient, owner: dict, session: Session) -> None:
    created = make_retainer(client, owner)
    assert created["client"] == {"id": owner["id"], "name": "Northwind Coffee", "avatar_url": None}
    assert created["ask_via"] == owner["contacts"][0]
    assert created["active"] is True
    assert created["ended_on"] is None
    assert get(client, created["id"]) == created

    other = make_client(client, "Pixelforge", contacts=(("line", "sora"),))
    moved = put_retainer(
        client,
        created,
        client_id=other["id"],
        ask_via_id=other["contacts"][0]["id"],
        amount=120,
        due_day=20,
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["client"]["name"] == "Pixelforge"
    assert moved.json()["ask_via"]["kind"] == "line"

    pay(client, created["id"], "2026-10-01")
    session.add(ReminderLog(client_id=other["id"], slot_on=TODAY, sent_at=at(TODAY)))
    session.commit()
    assert client.delete(f"/api/retainers/{created['id']}").status_code == 204
    assert client.get(f"/api/retainers/{created['id']}").status_code == 404
    assert session.scalars(select(RetainerPayment)).all() == []
    # With its retainer gone, the client can be deleted, along with its reminder history.
    assert client.delete(f"/api/clients/{other['id']}").status_code == 204
    assert session.scalars(select(ReminderLog)).all() == []


def test_list_filter_and_order(client: TestClient) -> None:
    pixel = make_client(client, "pixelforge")
    aurora = make_client(client, "Aurora Studio")
    ended = make_retainer(client, aurora, started_on="2026-01-01", ended_on="2026-02-01")
    first = make_retainer(client, pixel)
    second = make_retainer(client, aurora)
    assert [r["id"] for r in client.get("/api/retainers").json()] == [
        second["id"],
        first["id"],
        ended["id"],
    ]
    listed = client.get(f"/api/retainers?client_id={pixel['id']}").json()
    assert [r["id"] for r in listed] == [first["id"]]
    assert client.get("/api/retainers?client_id=999999").json() == []


def test_retainers_for_a_shared_project(client: TestClient, owner: dict) -> None:
    """One project, e.g. a bot, can be paid for monthly by several clients."""
    body = {"client_id": owner["id"], "name": "Giveaway bot", "price": 6000}
    project = client.post("/api/projects", json=body | {"started_on": "2026-09-01"}).json()
    other = make_client(client, "Pixelforge")
    mine = make_retainer(client, owner, project_id=project["id"])
    theirs = make_retainer(client, other, project_id=project["id"])
    make_retainer(client, other)  # another fee of theirs, for no project
    assert theirs["project"] == {"id": project["id"], "name": "Giveaway bot"}

    listed = client.get(f"/api/retainers?project_id={project['id']}").json()
    assert {r["id"] for r in listed} == {mine["id"], theirs["id"]}
    assert put_retainer(client, theirs, project_id=None).json()["project"] is None
    assert put_retainer(client, theirs, project_id=999999).status_code == 404
    assert client.post("/api/retainers", json={**mine, "project_id": 999999}).status_code == 404

    # Deleting the project keeps its retainers, just without the link.
    assert client.delete(f"/api/projects/{project['id']}").status_code == 204
    mine = get(client, mine["id"])
    assert (mine["project_id"], mine["project"]) == (None, None)


def test_ask_via_must_belong_to_the_client(client: TestClient, owner: dict) -> None:
    other = make_client(client, "Pixelforge")
    body = {
        "client_id": owner["id"],
        "amount": 250,
        "due_day": 25,
        "collection": "ask",
        "ask_via_id": other["contacts"][0]["id"],
        "started_on": "2026-10-01",
    }
    response = client.post("/api/retainers", json=body)
    assert response.status_code == 422
    assert response.json()["detail"] == "Pick one of this client's contacts"
    assert client.post("/api/retainers", json=body | {"ask_via_id": 999999}).status_code == 422
    # Without a contact is fine; reminders then just don't say where to ask.
    assert client.post("/api/retainers", json=body | {"ask_via_id": None}).status_code == 201

    retainer = make_retainer(client, owner)
    assert put_retainer(client, retainer, client_id=other["id"]).status_code == 422


def test_deleting_the_contact_clears_ask_via(client: TestClient, owner: dict) -> None:
    retainer = make_retainer(client, owner)
    contact_id = owner["contacts"][0]["id"]
    assert client.delete(f"/api/clients/{owner['id']}/contacts/{contact_id}").status_code == 204
    retainer = get(client, retainer["id"])
    assert (retainer["ask_via_id"], retainer["ask_via"]) == (None, None)


@pytest.mark.parametrize(
    "changes",
    [
        {"amount": 0},
        {"amount": -5},
        {"amount": 2_000_000_001},
        {"due_day": 0},
        {"due_day": 32},
        {"collection": "cash"},
        {"started_on": None},
        {"ended_on": "2026-09-30"},  # before the start
        {"collection": "auto_transfer"},  # auto with a contact to ask on
    ],
)
def test_invalid_retainer(client: TestClient, owner: dict, changes: dict) -> None:
    body = {
        "client_id": owner["id"],
        "amount": 250,
        "due_day": 25,
        "collection": "ask",
        "ask_via_id": owner["contacts"][0]["id"],
        "started_on": "2026-10-01",
    }
    assert client.post("/api/retainers", json=body | changes).status_code == 422


def test_missing_things(client: TestClient, owner: dict) -> None:
    body = {
        "client_id": 999999,
        "amount": 250,
        "due_day": 25,
        "collection": "auto_transfer",
        "started_on": "2026-10-01",
    }
    assert client.post("/api/retainers", json=body).status_code == 404
    assert client.get("/api/retainers/999999").status_code == 404
    body["client_id"] = owner["id"]
    assert client.put("/api/retainers/999999", json=body).status_code == 404
    assert client.delete("/api/retainers/999999").status_code == 404
    assert pay(client, 999999, "2026-10-01").status_code == 404


def test_payment_rules(client: TestClient, owner: dict) -> None:
    retainer = make_retainer(client, owner, started_on="2026-09-01")
    auto = make_retainer(client, owner, collection="auto_transfer")

    response = pay(client, auto["id"], "2026-10-01")
    assert response.status_code == 409
    assert "Auto transfers" in response.json()["detail"]
    response = pay(client, retainer["id"], "2026-08-01")  # before the start month
    assert response.status_code == 409
    assert response.json()["detail"] == "This retainer doesn't bill August 2026"

    assert pay(client, retainer["id"], "2026-10-01").status_code == 201
    response = pay(client, retainer["id"], "2026-10-31")
    assert response.status_code == 409
    assert response.json()["detail"] == "October 2026 is already recorded as paid"
    # A future month can be paid ahead.
    assert pay(client, retainer["id"], "2026-11-01").status_code == 201

    url = f"/api/retainers/{retainer['id']}/payments"
    valid = {"period": "2026-09-01", "amount": 250, "paid_on": str(TODAY)}
    for body in [{"amount": 0}, {"amount": 1.5}, {"paid_on": None}, {"period": "October"}]:
        assert client.post(url, json=valid | body).status_code == 422, body


def test_delete_payment(client: TestClient, owner: dict) -> None:
    retainer = make_retainer(client, owner)
    other = make_retainer(client, owner)
    payment = pay(client, retainer["id"], "2026-10-01").json()
    url = f"/api/retainers/{other['id']}/payments/{payment['id']}"
    assert client.delete(url).status_code == 404
    url = f"/api/retainers/{retainer['id']}/payments/{payment['id']}"
    assert client.delete(url).status_code == 204
    assert client.delete(url).status_code == 404
    assert get(client, retainer["id"])["this_month"]["status"] == "upcoming"


def test_edits_must_keep_recorded_payments_valid(client: TestClient, owner: dict) -> None:
    retainer = make_retainer(client, owner, started_on="2026-09-01")
    pay(client, retainer["id"], "2026-09-01")

    response = put_retainer(client, retainer, collection="auto_transfer", ask_via_id=None)
    assert response.status_code == 409
    response = put_retainer(client, retainer, started_on="2026-10-01", tracked_from="2026-10-01")
    assert response.status_code == 409
    assert "September 2026" in response.json()["detail"]
    assert get(client, retainer["id"])["started_on"] == "2026-09-01"  # unchanged

    assert put_retainer(client, retainer, amount=300, ended_on="2026-12-31").status_code == 200


# Paying several months ahead


def test_paying_several_months_ahead(
    client: TestClient, owner: dict, session: Session, webhook: list[str], pin
) -> None:
    retainer = make_retainer(client, owner, due_day=1, started_on="2027-01-01")
    pin(at("2027-01-01"))
    response = pay(client, retainer["id"], "2027-01-01", months=3, amount=750, paid_on="2027-01-01")
    assert response.status_code == 201, response.text
    payment = response.json()
    assert (payment["months"], payment["amount"]) == (3, 750)

    retainer = get(client, retainer["id"])
    assert {m["period"]: (m["status"], m["amount"]) for m in retainer["months"]} == {
        "2027-01-01": ("paid", 250),
        "2027-02-01": ("paid", 250),
        "2027-03-01": ("paid", 250),
        "2027-04-01": ("upcoming", 250),
    }
    assert retainer["this_month"]["payment"] == payment
    assert (retainer["next_due_on"], retainer["received"]) == ("2027-04-01", 750)
    data = overview(client)
    assert data["collected"]["received"] == 250  # January's share
    assert data["next_reminder"]["periods"] == ["2027-04-01"]
    assert data["next_reminder"]["at"] == "2027-04-01T09:00:00+08:00"

    # No reminders until April.
    for day in ("2027-01-01", "2027-02-01", "2027-03-01", "2027-03-31"):
        assert reminders.send_due(session, at(day, 9)) == 0
    assert reminders.send_due(session, at("2027-04-01", 9)) == 1
    assert webhook == [
        f"<@{USER_ID}> Ask Northwind Coffee for NT$250 (April) on Discord @danpark"
        + record(retainer, "2027-04")
    ]

    # Removing the payment leaves all three months unpaid.
    url = f"/api/retainers/{retainer['id']}/payments/{payment['id']}"
    assert client.delete(url).status_code == 204
    retainer = get(client, retainer["id"])
    assert (retainer["this_month"]["status"], retainer["next_due_on"]) == ("due", "2027-01-01")


def test_paying_ahead_rules(client: TestClient, owner: dict) -> None:
    retainer = make_retainer(client, owner, started_on="2026-10-01", ended_on="2027-01-31")
    assert pay(client, retainer["id"], "2026-11-01").status_code == 201

    response = pay(client, retainer["id"], "2026-10-01", months=3, amount=750)
    assert response.status_code == 409
    assert response.json()["detail"] == "November 2026 is already recorded as paid"
    response = pay(client, retainer["id"], "2026-12-01", months=3, amount=750)
    assert response.status_code == 409
    assert response.json()["detail"] == "This retainer doesn't bill February 2027"
    for months in (0, 13):
        assert pay(client, retainer["id"], "2026-12-01", months=months).status_code == 422
    assert pay(client, retainer["id"], "2026-12-01", months=2, amount=500).status_code == 201

    # Edits must keep every covered month billed, not just the first.
    response = put_retainer(client, retainer, ended_on="2026-12-31")
    assert response.status_code == 409
    assert "January 2027" in response.json()["detail"]


def test_a_payment_splits_evenly_over_its_months() -> None:
    payment = RetainerPayment(
        period=date(2026, 12, 1), months=3, amount=1000, paid_on=date(2026, 12, 1)
    )
    retainer = transient(started_on=date(2026, 12, 1), payments=[payment])
    months = [maintenance.month(retainer, p, TODAY) for p in maintenance.covered(payment)]
    assert [m.amount for m in months] == [334, 333, 333]  # the remainder goes first
    assert {m.status for m in months} == {MonthStatus.PAID}


@pytest.mark.parametrize(
    ("period", "months", "expected"),
    [
        ("2027-01-01", 1, "Jan 2027"),
        ("2027-01-01", 3, "Jan–Mar 2027"),
        ("2026-12-01", 3, "Dec 2026–Feb 2027"),
    ],
)
def test_month_range(period: str, months: int, expected: str) -> None:
    payment = RetainerPayment(period=date.fromisoformat(period), months=months)
    assert maintenance.month_range(payment) == expected


# Track from


def test_tracked_from_defaults_and_validation(client: TestClient, owner: dict) -> None:
    retainer = make_retainer(client, owner, started_on="2026-05-14")
    assert retainer["tracked_from"] == "2026-05-01"  # the start month
    retainer = make_retainer(client, owner, started_on="2026-05-14", tracked_from="2026-10-23")
    assert retainer["tracked_from"] == "2026-10-01"  # any day names its month
    # Between the start month and the end date, both included.
    assert make_retainer(client, owner, started_on="2026-05-14", tracked_from="2026-05-01")
    ended = {"started_on": "2026-05-14", "ended_on": "2026-09-01", "tracked_from": "2026-09-01"}
    assert make_retainer(client, owner, **ended)

    body = {"client_id": owner["id"], "amount": 250, "due_day": 25, "collection": "ask"}
    for bad in [
        {"started_on": "2026-05-14", "tracked_from": "2026-04-01"},
        {"started_on": "2026-05-14", "ended_on": "2026-08-31", "tracked_from": "2026-09-01"},
        {"started_on": "2026-05-14", "tracked_from": "not a month"},
    ]:
        assert client.post("/api/retainers", json=body | bad).status_code == 422, bad


def test_months_before_tracked_from_are_settled(
    client: TestClient, owner: dict, session: Session, webhook: list[str]
) -> None:
    ask = make_retainer(client, owner, started_on="2026-03-14", tracked_from="2026-10-01")
    # March to September are settled: not overdue, not in the history, not reminded.
    assert ask["overdue"] == []
    assert [m["period"] for m in ask["months"]] == ["2026-10-01"]
    assert ask["this_month"]["status"] == "upcoming"
    assert ask["active"] is True  # started_on still says when it really began
    response = pay(client, ask["id"], "2026-09-01")
    assert response.status_code == 409
    assert (
        response.json()["detail"]
        == "September 2026 is before tracking starts, so it counts as settled"
    )
    assert (
        pay(client, ask["id"], "2026-02-01").json()["detail"]
        == "This retainer doesn't bill February 2026"
    )
    assert reminders.send_due(session, at("2026-10-23", 9)) == 0
    assert overview(client)["next_reminder"]["at"] == "2026-10-25T09:00:00+08:00"
    assert overview(client, month="2026-09")["calendar"] == []

    # Moving tracking later than a recorded payment would hide it.
    pay(client, ask["id"], "2026-10-01")
    assert put_retainer(client, ask, tracked_from="2026-11-01").status_code == 409
    # Moving it earlier brings the months back as owed.
    moved = put_retainer(client, ask, tracked_from="2026-08-01").json()
    assert [m["period"] for m in moved["overdue"]] == ["2026-08-01", "2026-09-01"]


def test_settled_months_are_left_out_of_totals(
    client: TestClient, owner: dict, session: Session
) -> None:
    auto = make_retainer(
        client,
        owner,
        collection="auto_transfer",
        amount=300,
        due_day=10,
        started_on="2026-03-10",
        tracked_from="2026-09-01",
    )
    assert auto["received"] == 600  # September and October only
    ask = make_retainer(
        client, owner, amount=100, started_on="2026-03-01", tracked_from="2026-09-01"
    )
    # A payment for a settled month (only possible outside the API) still doesn't count.
    session.add(
        RetainerPayment(
            retainer_id=ask["id"], period=date(2026, 8, 1), amount=100, paid_on=date(2026, 8, 25)
        )
    )
    session.commit()
    assert get(client, ask["id"])["received"] == 0

    earnings = client.get("/api/overview/earnings").json()
    assert earnings["months"][2:10] == [0, 0, 0, 0, 0, 0, 300, 300]  # March to October
    assert earnings["total"] == 600


# Overview


def test_overview(client: TestClient, pin) -> None:
    northwind = make_client(client)
    pixel = make_client(client, "Pixelforge", contacts=(("discord", "@sora.px"),))
    kenji = make_client(client, "Kenji Tanaka", contacts=())
    aurora = make_client(client, "Aurora Studio", contacts=(("line", "mei.aurora"),))
    lumen = make_client(client, "Lumen Clinic", contacts=())

    make_retainer(client, northwind, started_on="2026-05-01")
    pf = make_retainer(client, pixel, amount=120, due_day=20, started_on="2026-09-01")
    pay(client, pf["id"], "2026-09-01")
    make_retainer(client, kenji, amount=180, due_day=1, collection="auto_transfer")
    au = make_retainer(client, aurora, amount=200, due_day=5, started_on="2026-06-01")
    for month in ("06", "07", "08", "09", "10"):
        pay(client, au["id"], f"2026-{month}-01", amount=200, paid_on=f"2026-{month}-06")
    make_retainer(client, lumen, amount=300, due_day=10, collection="auto_transfer")
    tiny = make_retainer(client, northwind, amount=1)  # paid early, shares the 25th
    pay(client, tiny["id"], "2026-10-01", amount=1)
    data = overview(client)

    assert data["today"] == "2026-10-23"
    assert data["month"] == "2026-10-01"
    assert data["active_count"] == 6
    assert data["monthly_total"] == 250 + 120 + 180 + 200 + 300 + 1
    # Northwind's months before October were never recorded, so they are overdue too.
    assert data["collected"] == {
        "period": "2026-10-01",
        "received": 180 + 200 + 300 + 1,
        "expected": 250 + 120 + 180 + 200 + 300 + 1,
        "paid": 4,
        "count": 6,
    }
    assert data["automatic"] == {"amount": 480, "clients": 2}
    assert [(o["client"]["name"], o["period"], o["days"]) for o in data["overdue"]] == [
        ("Northwind Coffee", "2026-05-01", 151),
        ("Northwind Coffee", "2026-06-01", 120),
        ("Northwind Coffee", "2026-07-01", 90),
        ("Northwind Coffee", "2026-08-01", 59),
        ("Northwind Coffee", "2026-09-01", 28),
        ("Pixelforge", "2026-10-01", 3),
    ]
    assert all(o["last_reminded_on"] is None for o in data["overdue"])

    days = {d["day"]: d for d in data["calendar"]}
    assert {day: d["status"] for day, d in days.items()} == {
        "2026-10-01": "paid",
        "2026-10-05": "paid",
        "2026-10-10": "paid",
        "2026-10-20": "overdue",
        "2026-10-25": "upcoming",
    }
    # The tiny paid retainer shares the 25th; the day shows the more urgent status.
    assert [e["status"] for e in days["2026-10-25"]["entries"]] == ["upcoming", "paid"]

    assert data["retainers"][0]["client"]["name"] == "Aurora Studio"
    assert data["reminders"] == {
        "enabled": False,
        "mention_user_id": None,
        "mention": None,
        "timezone": "Asia/Taipei",
        "time": "09:00",
        "repeat_days": 2,
    }
    # The oldest unsent slot comes first: Northwind's May reminder is waiting to go out.
    assert data["next_reminder"]["client"]["name"] == "Northwind Coffee"
    assert data["next_reminder"]["pending"] is True

    november = overview(client, month="2026-11")
    assert november["month"] == "2026-11-01"
    assert {d["status"] for d in november["calendar"]} == {"upcoming"}


@pytest.mark.parametrize("month", ["2026-13", "2026-1", "October", "2026-10-01"])
def test_overview_rejects_bad_months(client: TestClient, month: str) -> None:
    assert client.get("/api/maintenance", params={"month": month}).status_code == 422


def test_overview_empty(client: TestClient) -> None:
    data = overview(client)
    assert data["retainers"] == []
    assert data["next_reminder"] is None
    assert data["collected"]["count"] == 0
    assert data["calendar"] == []


# Client stats


def test_client_stats_and_flags(client: TestClient, pin) -> None:
    northwind = make_client(client)
    pixel = make_client(client, "Pixelforge")
    kenji = make_client(client, "Kenji Tanaka", contacts=())
    aurora = make_client(client, "Aurora Studio", contacts=(("line", "mei.aurora"),))
    hartmann = make_client(client, "Hartmann Legal", contacts=())

    make_retainer(client, northwind)  # due Sun 25 Oct
    make_retainer(client, pixel, amount=120, due_day=20)  # overdue since 20 Oct
    make_retainer(client, kenji, amount=180, due_day=1, collection="auto_transfer")
    au = make_retainer(client, aurora, amount=200, due_day=5)
    pay(client, au["id"], "2026-10-01", amount=200)
    # Ended and not-yet-started retainers don't count towards the monthly fee.
    make_retainer(client, hartmann, amount=999, started_on="2026-01-01", ended_on="2026-10-22")
    make_retainer(client, hartmann, amount=500, started_on="2026-10-24", due_day=1)

    def stats() -> dict[str, tuple]:
        return {
            c["name"]: (c["monthly_maintenance"], c["maintenance_flag"], c["maintenance_due_on"])
            for c in client.get("/api/clients").json()
        }

    assert stats() == {
        "Northwind Coffee": (250, "due", "2026-10-25"),
        "Pixelforge": (120, "overdue", None),
        "Kenji Tanaka": (180, "auto", None),
        "Aurora Studio": (200, None, None),
        "Hartmann Legal": (0, "overdue", None),  # its ended retainer still owes months
    }
    assert client.get(f"/api/clients/{northwind['id']}").json()["maintenance_flag"] == "due"

    # In its grace days a fee is still "due", not overdue.
    pin(at("2026-10-27"))
    assert stats()["Northwind Coffee"] == (250, "due", "2026-10-25")
    pin(at("2026-10-28"))
    assert stats()["Northwind Coffee"] == (250, "overdue", None)

    # A week later Hartmann's new retainer has started.
    pin(at("2026-10-30"))
    assert stats()["Hartmann Legal"][0] == 500
    assert stats()["Northwind Coffee"] == (250, "overdue", None)

    # "today" is taken in Taipei: 16:30 UTC on the 24th is already the 25th there.
    pin(datetime(2026, 10, 24, 16, 30, tzinfo=UTC))
    assert stats()["Hartmann Legal"][0] == 500
    pin(datetime(2026, 10, 23, 15, 59, tzinfo=UTC))
    assert stats()["Hartmann Legal"][0] == 0


# Reminder schedule: one combined reminder per client


def record(retainer: dict, month: str) -> str:
    """The link a reminder line ends with, opening Record payment for that month."""
    url = f"{settings.app_url}/maintenance?record={retainer['id']}&month={month}"
    return f" · [Record payment](<{url}>)"


def ask_retainer(client: TestClient, **fields: object) -> dict:
    owner = make_client(client)
    return make_retainer(client, owner, **fields)


def logged(session: Session) -> list[str]:
    rows = session.scalars(select(ReminderLog).order_by(ReminderLog.id))
    return [r.slot_on.isoformat() for r in rows]


def send_now(client: TestClient, client_id: int):
    return client.post("/api/maintenance/reminders/send", json={"client_id": client_id})


def test_reminder_at_nine_on_the_due_date(
    client: TestClient, session: Session, webhook: list[str]
) -> None:
    retainer = ask_retainer(client)  # due 25 Oct
    assert reminders.send_due(session, at("2026-10-24", 9)) == 0
    assert reminders.send_due(session, at("2026-10-25", 8, 59)) == 0
    assert webhook == []

    assert reminders.send_due(session, at("2026-10-25", 9)) == 1
    assert webhook == [
        f"<@{USER_ID}> Ask Northwind Coffee for NT$250 (October) on Discord @danpark"
        + record(retainer, "2026-10")
    ]
    assert logged(session) == ["2026-10-25"]

    # Never twice for the same slot, including after a restart (the log is in the database).
    assert reminders.send_due(session, at("2026-10-25", 9, 1)) == 0
    assert reminders.send_due(session, at("2026-10-25", 23, 59)) == 0
    assert len(webhook) == 1


def test_reminders_every_two_days_while_unpaid(
    client: TestClient, session: Session, webhook: list[str]
) -> None:
    retainer = ask_retainer(client)
    sent_on = []
    moment = at("2026-10-24", 0)
    while moment < at("2026-11-03", 0):
        if reminders.send_due(session, moment):
            sent_on.append(moment.strftime("%d %H:%M"))
        moment += timedelta(minutes=30)
    # The grace days don't change the rhythm: the due date, then every 2 days.
    assert sent_on == ["25 09:00", "27 09:00", "29 09:00", "31 09:00", "02 09:00"]

    pay(client, retainer["id"], "2026-10-01")
    assert reminders.send_due(session, at("2026-11-04", 9)) == 0
    assert len(webhook) == 5


def test_one_message_covers_every_month_and_retainer(
    client: TestClient, session: Session, webhook: list[str]
) -> None:
    owner = make_client(client)
    first = make_retainer(client, owner, started_on="2026-08-01")  # 25 Aug, 25 Sep, 25 Oct
    second = make_retainer(client, owner, amount=100, due_day=10, started_on="2026-10-01")  # 10 Oct

    # Anchored on the oldest unpaid due date, 25 Aug: slots fall every 2 days from then,
    # on 22, 24, 26 Oct.
    assert reminders.send_due(session, at("2026-10-22", 9)) == 1
    assert reminders.send_due(session, at("2026-10-23", 9)) == 0
    assert reminders.send_due(session, at("2026-10-24", 9)) == 1
    assert webhook[-1] == (
        f"<@{USER_ID}> Ask Northwind Coffee for NT$600 (August, September, October) "
        "on Discord @danpark" + record(first, "2026-08")
    )
    # Once October's main fee is due too, the next ping asks for everything.
    assert reminders.send_due(session, at("2026-10-26", 9)) == 1
    assert "NT$850 (August, September, October)" in webhook[-1]

    # Paying the oldest months moves the anchor to the next unpaid due date (10 Oct).
    pay(client, first["id"], "2026-08-01")
    pay(client, first["id"], "2026-09-01")
    assert reminders.send_due(session, at("2026-10-27", 9)) == 0
    assert reminders.send_due(session, at("2026-10-28", 9)) == 1
    # Record payment opens the oldest month left, now the other retainer's.
    assert webhook[-1].endswith(
        "for NT$350 (October) on Discord @danpark" + record(second, "2026-10")
    )


def test_several_clients_share_one_post(
    client: TestClient, session: Session, webhook: list[str]
) -> None:
    northwind = make_retainer(client, make_client(client), due_day=21, started_on="2026-09-01")
    aurora = make_client(client, "Aurora Studio", contacts=(("line", "mei.aurora"),))
    aurora_fee = make_retainer(client, aurora, amount=1200, due_day=21)
    make_retainer(client, aurora, amount=99, collection="auto_transfer", due_day=21)

    # Northwind's rhythm runs from 21 Sep, Aurora's from 21 Oct; both land on the 23rd.
    assert reminders.send_due(session, at("2026-10-23", 9)) == 2
    assert webhook == [
        (
            f"<@{USER_ID}> Maintenance reminders:\n"
            "- Ask Aurora Studio for NT$1,200 (October) on LINE mei.aurora"
            + record(aurora_fee, "2026-10")
            + "\n- Ask Northwind Coffee for NT$500 (September, October) on Discord @danpark"
            + record(northwind, "2026-09")
        )
    ]


def set_timezone(client: TestClient, name: str) -> None:
    current = client.get("/api/settings").json()
    response = client.put("/api/settings", json=current | {"timezone": name})
    assert response.status_code == 200, response.text


def test_reminder_time_follows_the_saved_timezone(
    client: TestClient, session: Session, webhook: list[str]
) -> None:
    ask_retainer(client)
    # 09:00 in Taipei is 01:00 UTC.
    assert reminders.send_due(session, datetime(2026, 10, 25, 0, 59, tzinfo=UTC)) == 0
    assert reminders.send_due(session, datetime(2026, 10, 25, 1, 0, tzinfo=UTC)) == 1

    # The loop reads the timezone on every tick, so a change applies without a restart.
    other = ask_retainer(client, due_day=26)
    set_timezone(client, "America/New_York")
    new_york = ZoneInfo("America/New_York")
    assert reminders.send_due(session, at("2026-10-26", 8, 59, tz=new_york)) == 0
    assert reminders.send_due(session, at("2026-10-26", 9, tz=new_york)) == 1
    slots = select(ReminderLog.slot_on).where(ReminderLog.client_id == other["client_id"])
    assert session.scalars(slots).all() == [date(2026, 10, 26)]


def test_changing_timezone_never_repeats_a_sent_day(
    client: TestClient, session: Session, webhook: list[str]
) -> None:
    ask_retainer(client)
    # Sent at 09:00 in Tokyo (08:00 in Taipei) on the due date...
    set_timezone(client, "Asia/Tokyo")
    assert reminders.send_due(session, at("2026-10-25", 9, tz=TOKYO)) == 1
    # ...then the user flies back to Taiwan. 09:00 Taipei is the same slot day: not resent.
    set_timezone(client, "Asia/Taipei")
    assert reminders.send_due(session, at("2026-10-25", 9)) == 0
    assert reminders.send_due(session, at("2026-10-26", 23)) == 0
    # The next slot comes at 09:00 in the new zone.
    assert reminders.send_due(session, at("2026-10-27", 8, 59)) == 0
    assert reminders.send_due(session, at("2026-10-27", 9)) == 1
    assert logged(session) == ["2026-10-25", "2026-10-27"]

    # A zone far behind turns back the local date; a day already sent still isn't repeated.
    set_timezone(client, "Pacific/Honolulu")
    honolulu = ZoneInfo("Pacific/Honolulu")
    assert reminders.send_due(session, at("2026-10-27", 9, tz=honolulu)) == 0
    assert len(webhook) == 2


def test_timezone_moves_today(client: TestClient, pin) -> None:
    owner = make_client(client)
    retainer = make_retainer(client, owner, due_day=21)
    # 23:30 on the 23rd in Taipei is already the 24th in Tokyo: day 2 vs day 3 of the grace.
    pin(at("2026-10-23", 23, 30))
    assert get(client, retainer["id"])["this_month"]["status"] == "due"
    set_timezone(client, "Asia/Tokyo")
    assert get(client, retainer["id"])["this_month"]["status"] == "overdue"
    data = overview(client)
    assert data["today"] == "2026-10-24"
    assert data["reminders"]["timezone"] == "Asia/Tokyo"


def test_missed_slot_is_sent_late_once(
    client: TestClient, session: Session, webhook: list[str]
) -> None:
    retainer = ask_retainer(client, due_day=20)
    # Down from before the 20th until the afternoon of the 25th: slots 20, 22 and 24 were
    # missed. Only the latest goes out, once, and counts for its own day.
    assert reminders.send_due(session, at("2026-10-25", 15)) == 1
    assert logged(session) == ["2026-10-24"]
    assert webhook == [
        f"<@{USER_ID}> Ask Northwind Coffee for NT$250 (October) on Discord @danpark"
        + record(retainer, "2026-10")
    ]
    assert reminders.send_due(session, at("2026-10-25", 16)) == 0
    assert reminders.send_due(session, at("2026-10-26", 9)) == 1
    assert len(webhook) == 2


def test_auto_transfers_get_no_reminders(
    client: TestClient, session: Session, webhook: list[str]
) -> None:
    owner = make_client(client)
    make_retainer(client, owner, collection="auto_transfer", started_on="2026-01-01")
    assert reminders.send_due(session, at("2026-10-25", 9)) == 0
    assert overview(client)["next_reminder"] is None
    response = send_now(client, owner["id"])
    assert response.status_code == 409
    assert response.json()["detail"] == "This client has nothing to ask for"
    assert webhook == []


def test_no_sends_without_a_webhook(client: TestClient, session: Session) -> None:
    retainer = ask_retainer(client, due_day=20)
    # conftest leaves the webhook unset and makes discord.post fail if called.
    assert reminders.send_due(session, at("2026-10-25", 9)) == 0
    assert logged(session) == []
    assert client.post("/api/maintenance/reminders/test").status_code == 409
    assert send_now(client, retainer["client_id"]).status_code == 409
    # The page still shows what would go out next.
    assert overview(client)["next_reminder"]["pending"] is True


def test_failed_post_is_retried(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch, webhook: list[str]
) -> None:
    ask_retainer(client)

    def broken(content: str) -> None:
        raise RuntimeError("Discord is down")

    monkeypatch.setattr(discord, "post", broken)
    with pytest.raises(RuntimeError):
        reminders.send_due(session, at("2026-10-25", 9))
    assert logged(session) == []

    monkeypatch.setattr(discord, "post", webhook.append)
    assert reminders.send_due(session, at("2026-10-25", 9, 1)) == 1


# Sending a client's reminder now


def test_next_reminder(client: TestClient, session: Session, webhook: list[str], pin) -> None:
    owner = make_client(client)
    make_retainer(client, owner)
    make_retainer(client, owner, amount=100, due_day=27)
    nxt = overview(client)["next_reminder"]
    assert nxt["client"]["name"] == "Northwind Coffee"
    assert nxt["periods"] == ["2026-10-01"]
    assert (nxt["due_on"], nxt["amount"]) == ("2026-10-25", 250)
    assert nxt["at"] == "2026-10-25T09:00:00+08:00"
    assert (nxt["pending"], nxt["last_reminded_on"]) == (False, None)

    # On the 27th the second fee is due as well: the ping asks for both.
    pin(at("2026-10-27", 8))
    nxt = overview(client)["next_reminder"]
    assert (nxt["at"], nxt["amount"], nxt["pending"]) == ("2026-10-25T09:00:00+08:00", 350, True)


def test_send_now_targets_one_client(
    client: TestClient, session: Session, webhook: list[str], pin
) -> None:
    northwind = make_client(client)
    make_retainer(client, northwind, due_day=20)
    pixel = make_client(client, "Pixelforge", contacts=(("discord", "@sora.px"),))
    pixel_fee = make_retainer(client, pixel, amount=120)  # nothing due yet: due 25 Oct

    response = send_now(client, pixel["id"])
    assert response.status_code == 200
    assert response.json() == {
        "content": f"<@{USER_ID}> Ask Pixelforge for NT$120 (October) on Discord @sora.px"
        + record(pixel_fee, "2026-10")
    }
    assert webhook == [response.json()["content"]]
    assert send_now(client, 999999).status_code == 404
    nxt = overview(client)["next_reminder"]
    assert nxt["client"]["name"] == "Northwind Coffee"  # Pixelforge's ping doesn't touch theirs

    # With something due, a manual send asks for what is due today, not fees still to come.
    make_retainer(client, northwind, amount=100)  # due 25 Oct
    assert "for NT$250 (October)" in send_now(client, northwind["id"]).json()["content"]


def test_send_now_marks_the_day(
    client: TestClient, session: Session, webhook: list[str], pin
) -> None:
    retainer = ask_retainer(client)  # slots on 25, 27, 29 Oct
    # Sent by hand early on the due date: the 09:00 slot that day doesn't repeat it.
    pin(at("2026-10-25", 8))
    assert send_now(client, retainer["client_id"]).status_code == 200
    assert logged(session) == ["2026-10-25"]
    assert overview(client)["next_reminder"]["at"] == "2026-10-27T09:00:00+08:00"
    assert overview(client)["next_reminder"]["last_reminded_on"] == "2026-10-25"
    assert reminders.send_due(session, at("2026-10-25", 9)) == 0

    # A manual ping on an off day keeps the rhythm: the 27th still goes out.
    pin(at("2026-10-26", 12))
    assert send_now(client, retainer["client_id"]).status_code == 200
    assert reminders.send_due(session, at("2026-10-27", 9)) == 1

    # After a missed slot, a manual send the next day stands in for it.
    pin(at("2026-10-30", 8))
    assert send_now(client, retainer["client_id"]).status_code == 200
    assert reminders.send_due(session, at("2026-10-30", 9)) == 0  # 29th missed, 30th reminded
    assert reminders.send_due(session, at("2026-10-31", 9)) == 1
    assert len(webhook) == 5

    # Once October is paid, a manual send is about the next fee coming up.
    pay(client, retainer["id"], "2026-10-01")
    response = send_now(client, retainer["client_id"])
    assert "for NT$250 (November)" in response.json()["content"]


def test_overdue_shows_when_the_client_was_last_reminded(
    client: TestClient, session: Session, webhook: list[str], pin
) -> None:
    retainer = ask_retainer(client, due_day=20)
    assert overview(client)["overdue"][0]["last_reminded_on"] is None
    send_now(client, retainer["client_id"])
    assert overview(client)["overdue"][0]["last_reminded_on"] == "2026-10-23"


def test_send_test(client: TestClient, webhook: list[str]) -> None:
    response = client.post("/api/maintenance/reminders/test")
    assert response.status_code == 200
    assert webhook == [f"<@{USER_ID}> {reminders.TEST_LINE}"]
    assert overview(client)["reminders"]["enabled"] is True
    assert overview(client)["reminders"]["mention_user_id"] == USER_ID


def test_discord_errors_become_502(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, webhook: list[str]
) -> None:
    import httpx2 as httpx

    def rejected(url: str, **kwargs: object) -> httpx.Response:
        request = httpx.Request("POST", url)
        return httpx.Response(404, request=request)

    monkeypatch.setattr(discord, "post", REAL_POST)
    monkeypatch.setattr(discord.httpx, "post", rejected)
    response = client.post("/api/maintenance/reminders/test")
    assert response.status_code == 502
    assert response.json()["detail"].startswith("Discord didn't take the message")


# Message text


def test_webhook_payload_mentions_only_the_user(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_post(url: str, **kwargs: object):
        calls.append((url, kwargs))
        return type("Ok", (), {"raise_for_status": lambda self: None})()

    monkeypatch.setattr(
        discord,
        "config",
        discord.Config(webhook_url="https://discord.test/hook", mention_user_id=USER_ID),
    )
    monkeypatch.setattr(discord.httpx, "post", fake_post)
    REAL_POST("hello")
    assert calls == [
        (
            "https://discord.test/hook",
            {
                "json": {"content": "hello", "allowed_mentions": {"users": [USER_ID]}},
                "timeout": 10,
            },
        )
    ]


def owed(*periods: str, amount: int = 250) -> list[Month]:
    return [
        Month(date.fromisoformat(p), date.fromisoformat(p), amount, MonthStatus.OVERDUE)
        for p in periods
    ]


@pytest.mark.parametrize(
    ("kind", "value", "months", "expected"),
    [
        ("discord", "@danpark", owed("2026-10-01"), "NT$250 (October) on Discord @danpark"),
        (
            "line",
            "mei.aurora",
            owed("2026-08-01", "2026-09-01", "2026-10-01"),
            "NT$750 (August, September, October) on LINE mei.aurora",
        ),
        # Two retainers due the same month name it once.
        (
            "email",
            "dan@nw.coffee",
            owed("2026-10-01", "2026-10-01"),
            "NT$500 (October) by email at dan@nw.coffee",
        ),
        (
            "other",
            "phone 0912",
            owed("2026-10-01", amount=1200),
            "NT$1,200 (October) via phone 0912",
        ),
        (None, None, owed("2025-12-01", "2026-01-01"), "NT$500 (December 2025, January)"),
    ],
)
def test_reminder_line(
    kind: str | None, value: str | None, months: list[Month], expected: str
) -> None:
    contact = ContactMethod(kind=ContactKind(kind), value=value) if kind else None
    line = maintenance.reminder_line("Northwind Coffee", months, contact, TODAY)
    assert line == f"Ask Northwind Coffee for {expected}"


def test_reminder_line_links() -> None:
    contact = ContactMethod(kind=ContactKind.DISCORD, value="@danpark", discord_user_id=123)
    url = "https://dash.example.com/maintenance?record=7&month=2026-10"
    line = maintenance.reminder_line("Northwind Coffee", owed("2026-10-01"), contact, TODAY, url)
    assert line == (
        "Ask Northwind Coffee for NT$250 (October) on Discord "
        "[@danpark](<https://discord.com/users/123>) · "
        "[Record payment](<https://dash.example.com/maintenance?record=7&month=2026-10>)"
    )


def test_message_mention() -> None:
    assert maintenance.message(["Ask A"], USER_ID) == f"<@{USER_ID}> Ask A"
    assert maintenance.message(["Ask A"], None) == "Ask A"
    assert maintenance.message(["Ask A", "Ask B"], USER_ID) == (
        f"<@{USER_ID}> Maintenance reminders:\n- Ask A\n- Ask B"
    )


def test_latest_slot() -> None:
    due = date(2026, 10, 20)
    cases = {
        at("2026-10-20", 8, 59): None,
        at("2026-10-20", 9): "2026-10-20",
        at("2026-10-21", 23, 59): "2026-10-20",
        at("2026-10-22", 8, 59): "2026-10-20",
        at("2026-10-22", 9): "2026-10-22",
        at("2026-10-23", 10): "2026-10-22",
        at("2027-01-01", 9): "2026-12-31",  # 73 days on: still every second day
    }
    for now, expected in cases.items():
        slot = maintenance.latest_slot(due, now, TAIPEI)
        assert (slot.isoformat() if slot else None) == expected, now


# Settings


DEFAULT_SETTINGS = {
    "timezone": "Asia/Taipei",
    "user_name": None,
    "studio_name": None,
    "studio_logo": None,
    "discord_webhook_url": None,
    "discord_mention_user_id": None,
    "discord_bot_token_set": False,
    "encryption_key_set": False,
}
LOGO = "data:image/png;base64,iVBORw0KGgo="


def test_settings(client: TestClient) -> None:
    assert client.get("/api/settings").json() == DEFAULT_SETTINGS
    response = client.put("/api/settings", json={"timezone": " Asia/Tokyo "})
    assert response.status_code == 200
    assert response.json() == DEFAULT_SETTINGS | {"timezone": "Asia/Tokyo"}
    assert client.get("/api/settings").json() == DEFAULT_SETTINGS | {"timezone": "Asia/Tokyo"}


def test_names_and_logo(client: TestClient) -> None:
    saved = {
        "timezone": "Asia/Taipei",
        "user_name": " Seria ",
        "studio_name": "Aurora Works",
        "studio_logo": LOGO,
    }
    response = client.put("/api/settings", json=saved)
    assert response.status_code == 200, response.text
    assert response.json() == DEFAULT_SETTINGS | saved | {"user_name": "Seria"}
    # Blank names clear them; a full update without the logo removes it.
    response = client.put(
        "/api/settings", json={"timezone": "Asia/Taipei", "user_name": "  ", "studio_name": ""}
    )
    assert response.json() == DEFAULT_SETTINGS


@pytest.mark.parametrize(
    "changes",
    [
        {"user_name": "x" * 61},
        {"studio_name": 9},
        {"studio_logo": "https://example.com/logo.png"},
        {"studio_logo": "data:image/svg+xml;base64,PHN2Zz4="},
        {"studio_logo": "data:image/png;base64,<script>"},
        {"studio_logo": "data:image/png;base64," + "A" * 200_000},
    ],
)
def test_bad_names_and_logos_are_rejected(client: TestClient, changes: dict) -> None:
    response = client.put("/api/settings", json={"timezone": "Asia/Taipei"} | changes)
    assert response.status_code == 422
    assert client.get("/api/settings").json() == DEFAULT_SETTINGS


HOOK = "https://discord.com/api/webhooks/123456789012345678/aBc-_9"


def test_discord_settings_turn_reminders_on(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def reminders() -> dict:
        return client.get("/api/maintenance").json()["reminders"]

    monkeypatch.setattr(settings, "encryption_key", SecretStr(KEY))
    assert reminders()["enabled"] is False
    saved = {
        "timezone": "Asia/Taipei",
        "discord_webhook_url": HOOK,
        "discord_mention_user_id": USER_ID,
    }
    response = client.put("/api/settings", json=saved)
    assert response.status_code == 200, response.text
    assert response.json() == DEFAULT_SETTINGS | saved | {"encryption_key_set": True}
    assert discord.config == discord.Config(webhook_url=HOOK, mention_user_id=USER_ID)
    # Stored encrypted.
    stored = session.get_one(AppSettings, 1).discord_webhook_url_encrypted
    assert stored is not None and HOOK not in stored
    assert crypto.decrypt(stored) == HOOK
    assert reminders()["enabled"] is True
    assert reminders()["mention_user_id"] == USER_ID

    # Blank clears them, turning reminders off.
    blank = {"timezone": "Asia/Taipei", "discord_webhook_url": " ", "discord_mention_user_id": ""}
    assert client.put("/api/settings", json=blank).json() == DEFAULT_SETTINGS | {
        "encryption_key_set": True
    }
    assert reminders()["enabled"] is False
    assert session.get_one(AppSettings, 1).discord_webhook_url_encrypted is None

    # Under a different key it can't be read, so reminders are off until it's entered again.
    client.put("/api/settings", json=saved)
    monkeypatch.setattr(settings, "encryption_key", SecretStr("x" * 32))
    discord.load(session)
    assert reminders()["enabled"] is False
    assert client.get("/api/settings").json()["discord_webhook_url"] is None


def test_webhook_needs_an_encryption_key(client: TestClient, session: Session) -> None:
    # conftest leaves ENCRYPTION_KEY unset; settings without a webhook still save.
    response = client.put(
        "/api/settings", json={"timezone": "Asia/Taipei", "discord_webhook_url": HOOK}
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Set ENCRYPTION_KEY on the API before saving a webhook URL"
    assert session.get_one(AppSettings, 1).discord_webhook_url_encrypted is None
    assert client.put("/api/settings", json={"timezone": "Asia/Tokyo"}).status_code == 200


@pytest.mark.parametrize(
    "changes",
    [
        # Only Discord's webhooks: the API posts to this URL.
        {"discord_webhook_url": "https://example.com/api/webhooks/1/x"},
        {"discord_webhook_url": "http://discord.com/api/webhooks/1/x"},
        {"discord_webhook_url": "https://discord.com.evil.test/api/webhooks/1/x"},
        {"discord_webhook_url": HOOK + "/../../users/@me"},
        {"discord_mention_user_id": "12345"},
        {"discord_mention_user_id": "<@123456789012345678>"},
    ],
)
def test_bad_discord_settings_are_rejected(client: TestClient, changes: dict) -> None:
    response = client.put("/api/settings", json={"timezone": "Asia/Taipei"} | changes)
    assert response.status_code == 422
    assert client.get("/api/settings").json() == DEFAULT_SETTINGS


@pytest.mark.parametrize(
    "name", ["Mars/Olympus", "asia/tokyo", "", "   ", "../etc/passwd", "/etc/localtime", None, 9]
)
def test_unknown_timezone_is_rejected(client: TestClient, name: object) -> None:
    response = client.put("/api/settings", json={"timezone": name})
    assert response.status_code == 422
    assert client.get("/api/settings").json() == DEFAULT_SETTINGS
