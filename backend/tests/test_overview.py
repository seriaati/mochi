"""The Overview page's earnings by month.

The clock is pinned: "now" is Friday 23 October 2026, 10:00 in Asia/Taipei (the default
timezone) unless a test moves it."""

from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.clock import get_now
from app.main import app

TAIPEI = ZoneInfo("Asia/Taipei")
TODAY = date(2026, 10, 23)


@pytest.fixture(autouse=True)
def pin() -> Iterator[Callable[[datetime], None]]:
    """Pins the API's clock; call it to move to another moment."""

    def move(moment: datetime) -> None:
        app.dependency_overrides[get_now] = lambda: moment

    move(datetime.combine(TODAY, time(10), TAIPEI))
    yield move
    app.dependency_overrides.pop(get_now, None)


@pytest.fixture
def owner(client: TestClient) -> dict:
    response = client.post("/api/clients", json={"name": "Northwind Coffee"})
    assert response.status_code == 201, response.text
    return response.json()


def make_project(client: TestClient, owner: dict, **fields: object) -> dict:
    body = {
        "client_id": owner["id"],
        "name": "Online ordering site",
        "price": 100_000,
        "started_on": "2024-01-01",
        **fields,
    }
    response = client.post("/api/projects", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def pay_project(
    client: TestClient, project: dict, amount: int, paid_on: str, addition_id: int | None = None
) -> None:
    body = {"amount": amount, "paid_on": paid_on, "addition_id": addition_id}
    response = client.post(f"/api/projects/{project['id']}/payments", json=body)
    assert response.status_code == 201, response.text


def make_retainer(client: TestClient, owner: dict, **fields: object) -> dict:
    body = {
        "client_id": owner["id"],
        "amount": 1_000,
        "due_day": 25,
        "collection": "auto_transfer",
        "started_on": "2026-01-01",
        **fields,
    }
    response = client.post("/api/retainers", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def pay_retainer(client: TestClient, retainer: dict, period: str, amount: int, paid_on: str):
    body = {"period": period, "amount": amount, "paid_on": paid_on}
    response = client.post(f"/api/retainers/{retainer['id']}/payments", json=body)
    assert response.status_code == 201, response.text


def earnings(client: TestClient, **params: int) -> dict:
    response = client.get("/api/overview/earnings", params=params)
    assert response.status_code == 200, response.text
    return response.json()


MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def months(**amounts: int) -> list[int]:
    """Twelve monthly totals from e.g. jan=500, oct=1000."""
    return [amounts.get(name, 0) for name in MONTHS]


def test_empty_year(client: TestClient) -> None:
    assert earnings(client) == {
        "year": 2026,
        "months": [0] * 12,
        "total": 0,
        "previous_total": 0,
        "change_percent": None,
    }


def test_project_and_addition_payments_by_day_paid(client: TestClient, owner: dict) -> None:
    project = make_project(client, owner)
    pay_project(client, project, 30_000, "2026-02-14")
    pay_project(client, project, 20_000, "2026-02-28")
    pay_project(client, project, 10_000, "2026-10-23")  # today counts
    pay_project(client, project, 5_000, "2026-10-24")  # tomorrow doesn't, yet
    addition = client.post(
        f"/api/projects/{project['id']}/additions",
        json={"name": "Giveaway feature", "price": 4_000, "agreed_on": "2026-01-01"},
    ).json()
    pay_project(client, project, 1_500, "2026-07-01", addition["id"])
    pay_project(client, project, 2_500, "2026-10-01", addition["id"])

    result = earnings(client)
    assert result["months"] == months(feb=50_000, jul=1_500, oct=12_500)
    assert result["total"] == 64_000


def test_ask_payments_by_day_paid_not_month_paid_for(client: TestClient, owner: dict) -> None:
    retainer = make_retainer(client, owner, collection="ask", amount=800)
    pay_retainer(client, retainer, "2026-08-01", 800, "2026-09-03")  # August's fee, paid late
    pay_retainer(client, retainer, "2026-09-01", 750, "2026-09-25")
    pay_retainer(client, retainer, "2026-12-01", 800, "2026-10-20")  # paid ahead
    # Unpaid "ask" months, overdue or not, earn nothing.
    assert earnings(client)["months"] == months(sep=1_550, oct=800)


def test_auto_transfers_count_once_due(client: TestClient, owner: dict, pin) -> None:
    make_retainer(client, owner, amount=1_000, due_day=25)
    every_month = dict.fromkeys(MONTHS[:9], 1_000)  # January to September
    assert earnings(client)["months"] == months(**every_month)

    pin(datetime.combine(date(2026, 10, 25), time(0, 30), TAIPEI))  # due today
    result = earnings(client)
    assert result["months"] == months(**every_month, oct=1_000)
    assert result["total"] == 10_000


def test_retainers_starting_and_ending_mid_year(client: TestClient, owner: dict) -> None:
    # Starts after March's due date, so April is the first month; ends before July's.
    make_retainer(
        client, owner, amount=600, due_day=5, started_on="2026-03-10", ended_on="2026-07-04"
    )
    # 31st: falls due on the 30th in September, which comes after the start.
    make_retainer(client, owner, amount=400, due_day=31, started_on="2026-09-30")
    # Ended last year: nothing this year.
    make_retainer(
        client, owner, amount=999, due_day=1, started_on="2025-01-01", ended_on="2025-12-31"
    )

    assert earnings(client)["months"] == months(apr=600, may=600, jun=600, sep=400)


def test_months_at_year_boundaries(client: TestClient, owner: dict, pin) -> None:
    project = make_project(client, owner)
    pay_project(client, project, 7_000, "2025-12-31")
    pay_project(client, project, 3_000, "2026-01-01")
    make_retainer(
        client, owner, amount=500, due_day=31, started_on="2025-12-01", ended_on="2026-01-31"
    )

    assert earnings(client)["months"] == months(jan=3_500)
    last_year = earnings(client, year=2025)
    assert (last_year["year"], last_year["months"]) == (2025, months(dec=7_500))

    # 17:00 UTC on 31 December is already 1 January in Taipei, so it's the new year.
    pin(datetime(2026, 12, 31, 17, tzinfo=UTC))
    make_retainer(client, owner, amount=200, due_day=1, started_on="2027-01-01")
    result = earnings(client)
    assert (result["year"], result["months"]) == (2027, months(jan=200))


def test_comparison_with_the_same_period_last_year(client: TestClient, owner: dict) -> None:
    project = make_project(client, owner, price=500_000)
    pay_project(client, project, 10_000, "2025-03-01")
    pay_project(client, project, 2_000, "2025-10-23")  # same date: counts
    pay_project(client, project, 50_000, "2025-10-24")  # later in the year: doesn't
    pay_project(client, project, 15_000, "2026-02-01")
    pay_project(client, project, 2_000, "2026-06-01")

    result = earnings(client)
    assert (result["total"], result["previous_total"]) == (17_000, 12_000)
    assert result["change_percent"] == 42  # 41.7

    # A past year compares whole years.
    pay_project(client, project, 20_000, "2024-05-01")
    past = earnings(client, year=2025)
    assert (past["total"], past["previous_total"], past["change_percent"]) == (62_000, 20_000, 210)


def test_comparison_down_and_without_last_year(client: TestClient, owner: dict) -> None:
    project = make_project(client, owner)
    pay_project(client, project, 8_000, "2025-04-01")
    pay_project(client, project, 6_000, "2026-04-01")
    assert earnings(client)["change_percent"] == -25

    assert earnings(client, year=2024)["change_percent"] is None  # nothing in 2023
    future = earnings(client, year=2027)  # nothing received yet
    assert (future["total"], future["previous_total"], future["change_percent"]) == (0, 0, None)


@pytest.mark.parametrize("year", [0, 1, 10_000, "soon"])
def test_bad_years_are_rejected(client: TestClient, year: int | str) -> None:
    assert client.get("/api/overview/earnings", params={"year": year}).status_code == 422
