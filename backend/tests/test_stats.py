"""The Stats page's income ledger.

The clock is pinned: "now" is Friday 23 October 2026, 10:00 in Asia/Taipei (the default
timezone)."""

from collections.abc import Iterator
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.clock import get_now
from app.main import app

TODAY = date(2026, 10, 23)


@pytest.fixture(autouse=True)
def pin() -> Iterator[None]:
    moment = datetime.combine(TODAY, time(10), ZoneInfo("Asia/Taipei"))
    app.dependency_overrides[get_now] = lambda: moment
    yield
    app.dependency_overrides.pop(get_now, None)


def post(client: TestClient, path: str, body: dict) -> dict:
    response = client.post(path, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def entries(client: TestClient) -> list[dict]:
    response = client.get("/api/stats/income")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["today"] == "2026-10-23"
    return body["entries"]


def test_empty(client: TestClient) -> None:
    assert entries(client) == []


def test_every_kind_of_income_oldest_first(client: TestClient) -> None:
    northwind = post(client, "/api/clients", {"name": "Northwind Coffee"})
    lumen = post(client, "/api/clients", {"name": "Lumen"})
    project = post(
        client,
        "/api/projects",
        {
            "client_id": northwind["id"],
            "name": "Menu bot",
            "price": 50_000,
            "started_on": "2025-01-01",
        },
    )
    addition = post(
        client,
        f"/api/projects/{project['id']}/additions",
        {"name": "Giveaways", "price": 4_000, "agreed_on": "2025-03-01"},
    )
    payments = f"/api/projects/{project['id']}/payments"
    post(client, payments, {"amount": 25_000, "paid_on": "2025-01-05"})
    post(
        client, payments, {"amount": 4_000, "paid_on": "2025-03-10", "addition_id": addition["id"]}
    )
    post(client, payments, {"amount": 9_999, "paid_on": "2026-10-24"})  # tomorrow: not yet

    # Lumen pays for Northwind's bot by asking, and is late for September.
    asked = post(
        client,
        "/api/retainers",
        {
            "client_id": lumen["id"],
            "project_id": project["id"],
            "amount": 800,
            "due_day": 1,
            "collection": "ask",
            "started_on": "2026-08-01",
        },
    )
    retainer_payments = f"/api/retainers/{asked['id']}/payments"
    post(
        client, retainer_payments, {"period": "2026-08-01", "amount": 800, "paid_on": "2026-08-03"}
    )
    post(
        client, retainer_payments, {"period": "2026-09-01", "amount": 800, "paid_on": "2026-09-10"}
    )
    # Auto transfers count on each due date reached: September and October.
    post(
        client,
        "/api/retainers",
        {
            "client_id": northwind["id"],
            "amount": 1_000,
            "due_day": 20,
            "collection": "auto_transfer",
            "started_on": "2026-09-01",
        },
    )

    menu_bot = {"id": project["id"], "name": "Menu bot"}
    nw = {"id": northwind["id"], "name": "Northwind Coffee"}
    project_fields = {"collection": None, "days_late": None, "late": None}
    auto = {"collection": "auto_transfer", "days_late": 0, "late": False, "addition": None}
    assert entries(client) == [
        {"paid_on": "2025-01-05", "amount": 25_000, "source": "project", "client": nw,
         "project": menu_bot, "addition": None, **project_fields},
        {"paid_on": "2025-03-10", "amount": 4_000, "source": "addition", "client": nw,
         "project": menu_bot, "addition": {"id": addition["id"], "name": "Giveaways"},
         **project_fields},
        {"paid_on": "2026-08-03", "amount": 800, "source": "retainer",
         "client": {"id": lumen["id"], "name": "Lumen"}, "project": menu_bot, "addition": None,
         "collection": "ask", "days_late": 2, "late": False},
        {"paid_on": "2026-09-10", "amount": 800, "source": "retainer",
         "client": {"id": lumen["id"], "name": "Lumen"}, "project": menu_bot, "addition": None,
         "collection": "ask", "days_late": 9, "late": True},
        {"paid_on": "2026-09-20", "amount": 1_000, "source": "retainer", "client": nw,
         "project": None, **auto},
        {"paid_on": "2026-10-20", "amount": 1_000, "source": "retainer", "client": nw,
         "project": None, **auto},
    ]  # fmt: skip


def test_paying_ahead_is_never_late(client: TestClient) -> None:
    owner = post(client, "/api/clients", {"name": "Northwind Coffee"})
    retainer = post(
        client,
        "/api/retainers",
        {
            "client_id": owner["id"],
            "amount": 500,
            "due_day": 25,
            "collection": "ask",
            "started_on": "2026-01-01",
        },
    )
    path = f"/api/retainers/{retainer['id']}/payments"
    post(
        client,
        path,
        {"period": "2026-11-01", "months": 2, "amount": 1_000, "paid_on": "2026-10-01"},
    )

    [ahead] = entries(client)
    assert (ahead["paid_on"], ahead["amount"], ahead["days_late"]) == ("2026-10-01", 1_000, 0)
