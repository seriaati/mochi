from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.clock import get_now
from app.main import app
from app.models import Addition, Collection, ContactMethod, Project, Retainer

SNOWFLAKE = "123456789012345678"


def make_client(client: TestClient, **fields: object) -> dict:
    response = client.post("/api/clients", json={"name": "Northwind Coffee", **fields})
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_get(client: TestClient) -> None:
    created = make_client(client, contact_person="  Daniel Park ", notes="")
    assert created["name"] == "Northwind Coffee"
    assert created["contact_person"] == "Daniel Park"
    assert created["notes"] is None
    assert created["contacts"] == []
    assert created["project_count"] == 0
    assert created["lifetime_billed"] == 0
    assert created["monthly_maintenance"] == 0

    fetched = client.get(f"/api/clients/{created['id']}").json()
    assert fetched == created


def test_list_sorted_by_name(client: TestClient) -> None:
    make_client(client, name="pixelforge")
    make_client(client, name="Aurora Studio")
    names = [c["name"] for c in client.get("/api/clients").json()]
    assert names == ["Aurora Studio", "pixelforge"]


def test_update(client: TestClient) -> None:
    created = make_client(client, notes="old")
    response = client.put(
        f"/api/clients/{created['id']}", json={"name": "Northwind", "contact_person": "Dan"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Northwind"
    assert response.json()["contact_person"] == "Dan"
    assert response.json()["notes"] is None


@pytest.mark.parametrize("body", [{}, {"name": ""}, {"name": "   "}, {"name": "x" * 201}])
def test_invalid_client(client: TestClient, body: dict) -> None:
    assert client.post("/api/clients", json=body).status_code == 422


def test_missing_client(client: TestClient) -> None:
    assert client.get("/api/clients/999999").status_code == 404
    assert client.put("/api/clients/999999", json={"name": "X"}).status_code == 404
    assert client.delete("/api/clients/999999").status_code == 404


def test_delete_cascades_contacts(client: TestClient, session: Session) -> None:
    created = make_client(client)
    client.post(f"/api/clients/{created['id']}/contacts", json={"kind": "line", "value": "dan"})
    assert client.delete(f"/api/clients/{created['id']}").status_code == 204
    assert client.get(f"/api/clients/{created['id']}").status_code == 404
    assert session.query(ContactMethod).filter_by(client_id=created["id"]).count() == 0


def test_delete_with_project_conflicts(client: TestClient, session: Session) -> None:
    created = make_client(client)
    session.add(Project(client_id=created["id"], name="Site", price=1000, started_on=date.today()))
    session.commit()
    assert client.delete(f"/api/clients/{created['id']}").status_code == 409


def test_delete_with_retainer_conflicts(client: TestClient, session: Session) -> None:
    created = make_client(client)
    session.add(
        Retainer(
            client_id=created["id"],
            amount=250,
            due_day=25,
            collection=Collection.ASK,
            started_on=date.today(),
        )
    )
    session.commit()
    assert client.delete(f"/api/clients/{created['id']}").status_code == 409


def test_stats(client: TestClient, session: Session) -> None:
    created = make_client(client)
    other = make_client(client, name="Other")
    today = date.today()
    # Pin the API's "today" (Taipei time) to the same date, whatever this machine's timezone.
    app.dependency_overrides[get_now] = lambda: datetime.combine(
        today, time(12), ZoneInfo("Asia/Taipei")
    )
    site = Project(client_id=created["id"], name="Site", price=8000, started_on=today)
    site.additions = [
        Addition(name="Booking", price=1500, agreed_on=today),
        Addition(name="Blog", price=500, agreed_on=today),
    ]
    session.add_all(
        [
            site,
            Project(client_id=created["id"], name="Bot", price=3000, started_on=today),
            Project(client_id=other["id"], name="Elsewhere", price=99999, started_on=today),
            Retainer(
                client_id=created["id"],
                amount=250,
                due_day=25,
                collection=Collection.ASK,
                started_on=today,
            ),
            Retainer(
                client_id=created["id"],
                amount=100,
                due_day=1,
                collection=Collection.AUTO_TRANSFER,
                started_on=today,
                ended_on=today + timedelta(days=30),
            ),
            # Ended and not yet started retainers don't count.
            Retainer(
                client_id=created["id"],
                amount=1000,
                due_day=1,
                collection=Collection.ASK,
                started_on=today - timedelta(days=90),
                ended_on=today - timedelta(days=1),
            ),
            Retainer(
                client_id=created["id"],
                amount=2000,
                due_day=1,
                collection=Collection.ASK,
                started_on=today + timedelta(days=1),
            ),
        ]
    )
    session.commit()

    listed = {c["id"]: c for c in client.get("/api/clients").json()}
    stats = listed[created["id"]]
    assert stats["project_count"] == 2
    assert stats["lifetime_billed"] == 8000 + 1500 + 500 + 3000
    assert stats["monthly_maintenance"] == 350
    assert listed[other["id"]]["project_count"] == 1
    assert listed[other["id"]]["monthly_maintenance"] == 0
    assert client.get(f"/api/clients/{created['id']}").json() == stats


def test_contact_crud(client: TestClient) -> None:
    created = make_client(client)
    base = f"/api/clients/{created['id']}/contacts"

    response = client.post(
        base, json={"kind": "discord", "value": "@danpark", "discord_user_id": SNOWFLAKE}
    )
    assert response.status_code == 201
    contact = response.json()
    assert contact["discord_user_id"] == SNOWFLAKE  # a string, so JS keeps every digit

    response = client.put(f"{base}/{contact['id']}", json={"kind": "discord", "value": "@dan"})
    assert response.status_code == 200
    assert response.json() == {
        "id": contact["id"],
        "kind": "discord",
        "value": "@dan",
        "discord_user_id": None,
        "discord_profile": None,
    }

    client.post(base, json={"kind": "email", "value": "dan@northwind.coffee"})
    contacts = client.get(f"/api/clients/{created['id']}").json()["contacts"]
    assert [c["kind"] for c in contacts] == ["discord", "email"]

    assert client.delete(f"{base}/{contact['id']}").status_code == 204
    assert client.delete(f"{base}/{contact['id']}").status_code == 404
    assert len(client.get(f"/api/clients/{created['id']}").json()["contacts"]) == 1


def test_contact_of_other_client_is_not_found(client: TestClient) -> None:
    first, second = make_client(client), make_client(client, name="Other")
    contact = client.post(
        f"/api/clients/{first['id']}/contacts", json={"kind": "line", "value": "dan"}
    ).json()
    url = f"/api/clients/{second['id']}/contacts/{contact['id']}"
    assert client.put(url, json={"kind": "line", "value": "x"}).status_code == 404
    assert client.delete(url).status_code == 404
    assert (
        client.post("/api/clients/999999/contacts", json={"kind": "line", "value": "x"}).status_code
        == 404
    )


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "fax", "value": "123"},
        {"kind": "line", "value": ""},
        {"kind": "discord", "value": "@dan", "discord_user_id": "not-a-number"},
        {"kind": "discord", "value": "@dan", "discord_user_id": "12345"},
        {"kind": "discord", "value": "@dan", "discord_user_id": "9" * 20},
        {"kind": "line", "value": "dan", "discord_user_id": SNOWFLAKE},
    ],
)
def test_invalid_contact(client: TestClient, body: dict) -> None:
    created = make_client(client)
    assert client.post(f"/api/clients/{created['id']}/contacts", json=body).status_code == 422


def test_blank_discord_id_is_null(client: TestClient) -> None:
    created = make_client(client)
    response = client.post(
        f"/api/clients/{created['id']}/contacts",
        json={"kind": "discord", "value": "@dan", "discord_user_id": " "},
    )
    assert response.json()["discord_user_id"] is None
