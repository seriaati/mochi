from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import demo, maintenance
from app.config import settings
from app.main import app
from app.models import AppSettings, Client, Retainer
from tests.conftest import TEST_PASSWORD


@pytest.mark.parametrize(
    "today", [date(2026, 10, 26), date(2027, 1, 1), date(2027, 3, 3), date(2027, 3, 31)]
)
def test_reset_replaces_everything_with_sample_data(
    anon_client: TestClient, session: Session, today: date
) -> None:
    session.add(Client(name="Real client"))
    session.get_one(AppSettings, 1).timezone = "Europe/Paris"
    session.flush()

    for _ in range(2):  # and again the next day
        demo.wipe(session)
        demo.seed(session, today)

    assert session.scalars(select(Client.name).order_by(Client.id)).all() == [
        "Lantern Café",
        "Pixel Guild",
        "Northwind Studio",
        "Hoshi Bakery",
    ]
    assert session.get_one(AppSettings, 1).timezone == "Asia/Taipei"
    session.expire_all()
    overdue = {
        r.client.name: maintenance.overdue(r, today) for r in session.scalars(select(Retainer))
    }
    assert [m.days_late for m in overdue["Pixel Guild"]] == [5]
    assert overdue["Hoshi Bakery"] == overdue["Lantern Café"] == []

    # Logged out by the wipe, but the pages load once logged in again.
    assert session.scalar(select(func.count()).select_from(AppSettings)) == 1
    browser = TestClient(app, base_url="https://testserver")  # the cookie is Secure
    assert browser.post("/api/auth/login", json={"password": TEST_PASSWORD}).status_code == 200
    for path in [
        "/api/overview/earnings",
        "/api/maintenance",
        "/api/projects",
        "/api/clients",
        "/api/retainers",
    ]:
        assert browser.get(path).status_code == 200, path


def test_reset_needs_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "demo", False)
    with pytest.raises(SystemExit, match="DEMO"):
        demo.main(["reset"])
