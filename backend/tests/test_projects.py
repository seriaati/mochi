from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Addition, Payment, Project

TODAY = date.today()


def make_client(client: TestClient, name: str = "Northwind Coffee") -> dict:
    response = client.post("/api/clients", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def make_project(client: TestClient, client_id: int, **fields: object) -> dict:
    body = {
        "client_id": client_id,
        "name": "Online ordering site",
        "price": 48000,
        "started_on": str(TODAY - timedelta(days=30)),
        **fields,
    }
    response = client.post("/api/projects", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def put_project(client: TestClient, project: dict, **changes: object) -> dict:
    fields = ("client_id", "name", "description", "price", "deposit_percent")
    dates = ("started_on", "due_on", "delivered_on")
    body = {k: project[k] for k in fields + dates} | changes
    response = client.put(f"/api/projects/{project['id']}", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def make_addition(client: TestClient, project_id: int, **fields: object) -> dict:
    body = {"name": "Giveaway feature", "price": 500, "agreed_on": str(TODAY), **fields}
    response = client.post(f"/api/projects/{project_id}/additions", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def pay(client: TestClient, project_id: int, amount: int, addition_id: int | None = None):
    return client.post(
        f"/api/projects/{project_id}/payments",
        json={"amount": amount, "paid_on": str(TODAY), "addition_id": addition_id},
    )


def get(client: TestClient, project_id: int) -> dict:
    response = client.get(f"/api/projects/{project_id}")
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def owner(client: TestClient) -> dict:
    return make_client(client)


def test_create_and_get(client: TestClient, owner: dict) -> None:
    created = make_project(client, owner["id"], description="  ", due_on=str(TODAY + timedelta(23)))
    assert created["client"] == {
        "id": owner["id"],
        "name": "Northwind Coffee",
        "contact_person": None,
        "avatar_url": None,
    }
    assert created["description"] is None
    assert created["deposit_percent"] == 50
    assert created["delivered_on"] is None
    assert created["expected_deposit"] == 24000
    assert created["expected_final"] == 24000
    assert created["paid"] == 0
    assert created["outstanding"] == 48000
    assert created["deposit_due"] == 24000
    assert created["final_due"] == 24000
    assert created["status"] == "in_progress"
    assert created["additions"] == []
    assert created["payments"] == []
    assert created["additions_total"] == 0
    assert created["total"] == 48000
    assert created["total_paid"] == 0
    assert created["total_outstanding"] == 48000
    assert get(client, created["id"]) == created


def test_due_date_is_optional(client: TestClient, owner: dict) -> None:
    assert make_project(client, owner["id"])["due_on"] is None


@pytest.mark.parametrize(
    ("price", "percent", "deposit", "final"),
    [
        (48000, 50, 24000, 24000),
        (3001, 50, 1501, 1500),  # half rounds up
        (5, 50, 3, 2),  # half rounds up, not to even
        (5, 30, 2, 3),
        (999, 33, 330, 669),
        (1000, 33, 330, 670),
        (1, 50, 1, 0),
        (7, 10, 1, 6),
        (12345, 0, 0, 12345),
        (12345, 100, 12345, 0),
        (0, 50, 0, 0),
    ],
)
def test_deposit_split(
    client: TestClient, owner: dict, price: int, percent: int, deposit: int, final: int
) -> None:
    project = make_project(client, owner["id"], price=price, deposit_percent=percent)
    assert (project["expected_deposit"], project["expected_final"]) == (deposit, final)
    addition = make_addition(client, project["id"], price=price, deposit_percent=percent)
    assert (addition["expected_deposit"], addition["expected_final"]) == (deposit, final)


def test_status_transitions(client: TestClient, owner: dict) -> None:
    project = make_project(client, owner["id"], price=3001)
    assert pay(client, project["id"], 1501).status_code == 201
    project = get(client, project["id"])
    assert project["status"] == "in_progress"
    assert (project["paid"], project["deposit_due"], project["final_due"]) == (1501, 0, 1500)

    project = put_project(client, project, delivered_on=str(TODAY))
    assert project["status"] == "final_payment_due"

    assert pay(client, project["id"], 1500).status_code == 201
    project = get(client, project["id"])
    assert project["status"] == "done"
    assert (project["outstanding"], project["deposit_due"], project["final_due"]) == (0, 0, 0)

    # Delivery can be undone by editing; a fully paid project then counts as in progress again.
    project = put_project(client, project, delivered_on=None)
    assert project["status"] == "in_progress"


def test_partial_deposit(client: TestClient, owner: dict) -> None:
    project = make_project(client, owner["id"], price=10000)
    pay(client, project["id"], 2000)
    project = get(client, project["id"])
    assert (project["deposit_due"], project["final_due"], project["outstanding"]) == (
        3000,
        5000,
        8000,
    )


def test_free_project_is_done_on_delivery(client: TestClient, owner: dict) -> None:
    project = make_project(client, owner["id"], price=0, delivered_on=str(TODAY))
    assert project["status"] == "done"


def test_payment_kinds(client: TestClient, owner: dict) -> None:
    project = make_project(client, owner["id"], price=10000)
    pay(client, project["id"], 3000)
    pay(client, project["id"], 2000)
    pay(client, project["id"], 5000)
    assert [p["kind"] for p in get(client, project["id"])["payments"]] == [
        "deposit",
        "deposit",
        "final",
    ]

    straddle = make_project(client, owner["id"], price=10000)
    response = pay(client, straddle["id"], 6000)
    assert response.json()["kind"] == "payment"

    single = make_addition(client, project["id"], price=500)
    response = pay(client, project["id"], 500, single["id"])
    assert response.status_code == 201
    assert response.json() == {
        "id": response.json()["id"],
        "addition_id": single["id"],
        "amount": 500,
        "paid_on": str(TODAY),
        "note": None,
        "kind": "payment",
    }


def test_overpayment_guard(client: TestClient, owner: dict) -> None:
    project = make_project(client, owner["id"], price=3000)
    assert pay(client, project["id"], 3001).status_code == 409
    assert pay(client, project["id"], 1500).status_code == 201
    response = pay(client, project["id"], 1501)
    assert response.status_code == 409
    assert "NT$1,500" in response.json()["detail"]
    assert pay(client, project["id"], 1500).status_code == 201
    assert pay(client, project["id"], 1).status_code == 409

    # Each target is guarded on its own: the project is paid off, the addition isn't.
    addition = make_addition(client, project["id"], price=500)
    assert pay(client, project["id"], 501, addition["id"]).status_code == 409
    assert pay(client, project["id"], 500, addition["id"]).status_code == 201
    assert pay(client, project["id"], 1, addition["id"]).status_code == 409
    assert get(client, project["id"])["total_paid"] == 3500


@pytest.mark.parametrize("amount", [0, -100, 1.5, "abc"])
def test_invalid_payment_amount(client: TestClient, owner: dict, amount: object) -> None:
    project = make_project(client, owner["id"])
    response = client.post(
        f"/api/projects/{project['id']}/payments", json={"amount": amount, "paid_on": str(TODAY)}
    )
    assert response.status_code == 422


def test_price_cannot_drop_below_paid(client: TestClient, owner: dict) -> None:
    project = make_project(client, owner["id"], price=10000)
    pay(client, project["id"], 5000)
    response = client.put(
        f"/api/projects/{project['id']}",
        json={
            "client_id": owner["id"],
            "name": "x",
            "price": 4999,
            "started_on": project["started_on"],
        },
    )
    assert response.status_code == 409
    assert put_project(client, project, price=5000)["status"] == "in_progress"

    addition = make_addition(client, project["id"], price=800)
    pay(client, project["id"], 800, addition["id"])
    url = f"/api/projects/{project['id']}/additions/{addition['id']}"
    body = {"name": "Giveaway feature", "price": 799, "agreed_on": str(TODAY)}
    assert client.put(url, json=body).status_code == 409


def test_additions_on_a_done_project(client: TestClient, owner: dict) -> None:
    project = make_project(client, owner["id"], price=3000, delivered_on=str(TODAY))
    pay(client, project["id"], 3000)
    assert get(client, project["id"])["status"] == "done"

    single = make_addition(client, project["id"], name="Giveaway feature", price=500)
    assert single["deposit_percent"] == 0
    assert (single["expected_deposit"], single["expected_final"]) == (0, 500)
    assert (single["deposit_due"], single["final_due"]) == (0, 500)
    assert single["status"] == "in_progress"

    project = get(client, project["id"])
    # The project itself stays done; the unpaid addition shows in the totals.
    assert project["status"] == "done"
    assert project["outstanding"] == 0
    assert project["additions_total"] == 500
    assert project["total"] == 3500
    assert project["total_paid"] == 3000
    assert project["total_outstanding"] == 500
    assert project["additions"][0]["outstanding"] == 500

    url = f"/api/projects/{project['id']}/additions/{single['id']}"
    body = {"name": "Giveaway feature", "price": 500, "agreed_on": str(TODAY)}
    delivered = client.put(url, json=body | {"delivered_on": str(TODAY)}).json()
    assert delivered["status"] == "final_payment_due"
    pay(client, project["id"], 500, single["id"])
    project = get(client, project["id"])
    assert project["additions"][0]["status"] == "done"
    assert project["total_outstanding"] == 0

    # A split addition works like a project.
    split = make_addition(
        client, project["id"], name="Loyalty points", price=8001, deposit_percent=50
    )
    assert (split["expected_deposit"], split["expected_final"]) == (4001, 4000)
    pay(client, project["id"], 4001, split["id"])
    split = get(client, project["id"])["additions"][0]
    assert split["name"] == "Loyalty points"  # newest agreed first, then newest created
    assert (split["deposit_due"], split["final_due"], split["status"]) == (0, 4000, "in_progress")


def test_addition_validation(client: TestClient, owner: dict) -> None:
    project = make_project(client, owner["id"])
    base = f"/api/projects/{project['id']}/additions"
    for body in [
        {},
        {"name": "", "price": 1, "agreed_on": str(TODAY)},
        {"name": "x", "price": -1, "agreed_on": str(TODAY)},
        {"name": "x", "price": 1, "agreed_on": str(TODAY), "deposit_percent": 101},
        {
            "name": "x",
            "price": 1,
            "agreed_on": str(TODAY),
            "delivered_on": str(TODAY - timedelta(1)),
        },
    ]:
        assert client.post(base, json=body).status_code == 422, body


@pytest.mark.parametrize(
    "changes",
    [
        {"name": " "},
        {"price": -1},
        {"price": 2_000_000_001},
        {"deposit_percent": -1},
        {"deposit_percent": 101},
        {"due_on": str(TODAY - timedelta(days=31))},
        {"delivered_on": str(TODAY - timedelta(days=31))},
        {"started_on": None},
    ],
)
def test_invalid_project(client: TestClient, owner: dict, changes: dict) -> None:
    body = {
        "client_id": owner["id"],
        "name": "Site",
        "price": 1000,
        "started_on": str(TODAY - timedelta(days=30)),
    }
    assert client.post("/api/projects", json=body | changes).status_code == 422


def test_missing_things(client: TestClient, owner: dict) -> None:
    body = {"client_id": 999999, "name": "Site", "price": 1, "started_on": str(TODAY)}
    assert client.post("/api/projects", json=body).status_code == 404
    assert client.get("/api/projects/999999").status_code == 404
    assert (
        client.put("/api/projects/999999", json=body | {"client_id": owner["id"]}).status_code
        == 404
    )
    assert client.delete("/api/projects/999999").status_code == 404
    project = make_project(client, owner["id"])
    assert client.put(f"/api/projects/{project['id']}", json=body).status_code == 404
    assert pay(client, 999999, 100).status_code == 404
    assert pay(client, project["id"], 100, addition_id=999999).status_code == 404


def test_children_of_other_projects_are_not_found(client: TestClient, owner: dict) -> None:
    first = make_project(client, owner["id"])
    second = make_project(client, owner["id"], name="Other")
    addition = make_addition(client, first["id"])
    project_payment = pay(client, first["id"], 100).json()
    addition_payment = pay(client, first["id"], 100, addition["id"]).json()

    other = f"/api/projects/{second['id']}"
    body = {"name": "x", "price": 1, "agreed_on": str(TODAY)}
    assert client.put(f"{other}/additions/{addition['id']}", json=body).status_code == 404
    assert client.delete(f"{other}/additions/{addition['id']}").status_code == 404
    assert pay(client, second["id"], 100, addition["id"]).status_code == 404
    assert client.delete(f"{other}/payments/{project_payment['id']}").status_code == 404
    assert client.delete(f"{other}/payments/{addition_payment['id']}").status_code == 404


def test_addition_and_payment_crud(client: TestClient, owner: dict, session: Session) -> None:
    project = make_project(client, owner["id"])
    base = f"/api/projects/{project['id']}"
    addition = make_addition(client, project["id"], description="Spin the wheel")
    assert addition["project_id"] == project["id"]
    assert addition["description"] == "Spin the wheel"

    response = client.put(
        f"{base}/additions/{addition['id']}",
        json={"name": "Lucky draw", "price": 700, "deposit_percent": 50, "agreed_on": str(TODAY)},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Lucky draw"
    assert response.json()["description"] is None
    assert response.json()["expected_deposit"] == 350

    deposit = pay(client, project["id"], 24000).json()
    assert deposit["kind"] == "deposit"
    assert deposit["addition_id"] is None
    paid = pay(client, project["id"], 350, addition["id"]).json()
    assert [p["id"] for p in get(client, project["id"])["payments"]] == [deposit["id"], paid["id"]]

    assert client.delete(f"{base}/payments/{deposit['id']}").status_code == 204
    assert client.delete(f"{base}/payments/{deposit['id']}").status_code == 404
    project = get(client, project["id"])
    assert (project["paid"], project["total_paid"]) == (0, 350)

    # Deleting an addition takes its payments with it.
    assert client.delete(f"{base}/additions/{addition['id']}").status_code == 204
    assert client.delete(f"{base}/additions/{addition['id']}").status_code == 404
    assert session.scalar(select(Payment).where(Payment.id == paid["id"])) is None
    assert get(client, project["id"])["additions"] == []


def test_delete_project_cascades(client: TestClient, owner: dict, session: Session) -> None:
    project = make_project(client, owner["id"])
    keep = make_project(client, owner["id"], name="Keep")
    addition = make_addition(client, project["id"])
    pay(client, project["id"], 100)
    pay(client, project["id"], 100, addition["id"])
    pay(client, keep["id"], 100)

    assert client.delete(f"/api/projects/{project['id']}").status_code == 204
    assert client.get(f"/api/projects/{project['id']}").status_code == 404
    assert session.scalar(select(Addition).where(Addition.project_id == project["id"])) is None
    payments = session.scalars(select(Payment)).all()
    assert [(p.project_id, p.addition_id) for p in payments] == [(keep["id"], None)]

    # With its projects gone, the client can be deleted.
    assert client.delete(f"/api/clients/{owner['id']}").status_code == 409
    assert client.delete(f"/api/projects/{keep['id']}").status_code == 204
    assert client.delete(f"/api/clients/{owner['id']}").status_code == 204


def test_delete_project_with_unloaded_children(
    client: TestClient, owner: dict, session: Session
) -> None:
    """Children written outside the API (so not loaded on the project) are removed by the DB."""
    project = Project(client_id=owner["id"], name="Bot", price=3000, started_on=TODAY)
    project.additions = [Addition(name="Extra", price=500, agreed_on=TODAY)]
    session.add(project)
    session.flush()
    session.add_all(
        [
            Payment(project_id=project.id, amount=1500, paid_on=TODAY),
            Payment(addition_id=project.additions[0].id, amount=500, paid_on=TODAY),
        ]
    )
    session.commit()
    project_id = project.id
    session.expunge_all()
    assert client.delete(f"/api/projects/{project_id}").status_code == 204
    assert session.scalars(select(Payment)).all() == []
    assert session.scalars(select(Addition)).all() == []


def test_client_stats_follow_projects(client: TestClient, owner: dict) -> None:
    other = make_client(client, "Pixelforge")

    def stats(client_id: int) -> tuple[int, int]:
        listed = {c["id"]: c for c in client.get("/api/clients").json()}
        return listed[client_id]["project_count"], listed[client_id]["lifetime_billed"]

    site = make_project(client, owner["id"], price=8000)
    make_project(client, owner["id"], price=3000)
    addition = make_addition(client, site["id"], price=1500)
    make_addition(client, site["id"], price=500)
    assert stats(owner["id"]) == (2, 8000 + 3000 + 1500 + 500)
    assert stats(other["id"]) == (0, 0)

    # Payments don't change what was billed.
    pay(client, site["id"], 4000)
    assert stats(owner["id"]) == (2, 13000)

    client.delete(f"/api/projects/{site['id']}/additions/{addition['id']}")
    assert stats(owner["id"]) == (2, 11500)

    # Moving a project moves its additions' value too.
    put_project(client, get(client, site["id"]), client_id=other["id"])
    assert stats(owner["id"]) == (1, 3000)
    assert stats(other["id"]) == (1, 8500)
    assert client.get(f"/api/clients/{other['id']}").json()["lifetime_billed"] == 8500


def test_list_filter_and_order(client: TestClient, owner: dict) -> None:
    other = make_client(client, "Pixelforge")
    done = make_project(client, owner["id"], name="Done", price=100, delivered_on=str(TODAY))
    pay(client, done["id"], 100)
    make_project(client, owner["id"], name="No due date")
    make_project(client, owner["id"], name="Due later", due_on=str(TODAY + timedelta(days=60)))
    make_project(client, owner["id"], name="Due soon", due_on=str(TODAY + timedelta(days=8)))
    make_project(client, owner["id"], name="Awaiting payment", delivered_on=str(TODAY))
    make_project(client, other["id"], name="Elsewhere")

    names = [p["name"] for p in client.get(f"/api/projects?client_id={owner['id']}").json()]
    assert names == ["Awaiting payment", "Due soon", "Due later", "No due date", "Done"]
    assert len(client.get("/api/projects").json()) == 6
    assert client.get("/api/projects?client_id=999999").json() == []


def edit_payment(client: TestClient, project_id: int, payment_id: int, **fields: object):
    body = {"amount": 100, "paid_on": str(TODAY), "addition_id": None, **fields}
    return client.put(f"/api/projects/{project_id}/payments/{payment_id}", json=body)


def test_edit_payment(client: TestClient, owner: dict) -> None:
    project = make_project(client, owner["id"], price=10000)
    payment = pay(client, project["id"], 5000).json()
    response = edit_payment(
        client, project["id"], payment["id"], amount=4000, paid_on="2026-08-04", note=" transfer "
    )
    assert response.status_code == 200
    assert response.json() == {
        "id": payment["id"],
        "addition_id": None,
        "amount": 4000,
        "paid_on": "2026-08-04",
        "note": "transfer",
        "kind": "deposit",
    }
    project = get(client, project["id"])
    assert (project["paid"], project["deposit_due"], project["final_due"]) == (4000, 1000, 5000)
    assert len(project["payments"]) == 1


def test_edit_payment_overpayment_guard(client: TestClient, owner: dict) -> None:
    project = make_project(client, owner["id"], price=3000)
    first = pay(client, project["id"], 1000).json()
    pay(client, project["id"], 1500)
    # Its own amount doesn't count, so keeping, lowering or raising to the limit works.
    assert edit_payment(client, project["id"], first["id"], amount=1000).status_code == 200
    assert edit_payment(client, project["id"], first["id"], amount=1).status_code == 200
    assert edit_payment(client, project["id"], first["id"], amount=1500).status_code == 200
    response = edit_payment(client, project["id"], first["id"], amount=1501)
    assert response.status_code == 409
    assert "NT$1,500" in response.json()["detail"]
    assert get(client, project["id"])["paid"] == 3000
    for amount in (0, -1, 1.5):
        assert edit_payment(client, project["id"], first["id"], amount=amount).status_code == 422


def test_edit_payment_moves_between_targets(client: TestClient, owner: dict) -> None:
    project = make_project(client, owner["id"], price=3000)
    addition = make_addition(client, project["id"], price=500)
    payment = pay(client, project["id"], 500).json()

    moved = edit_payment(
        client, project["id"], payment["id"], amount=500, addition_id=addition["id"]
    )
    assert moved.status_code == 200
    assert moved.json()["addition_id"] == addition["id"]
    project = get(client, project["id"])
    assert (project["paid"], project["additions"][0]["paid"]) == (0, 500)

    # The guard applies to the new target: the addition is full, the project isn't.
    other = pay(client, project["id"], 3000).json()
    assert (
        edit_payment(client, project["id"], other["id"], addition_id=addition["id"]).status_code
        == 409
    )
    back = edit_payment(client, project["id"], payment["id"], amount=500)
    assert back.status_code == 409  # the project is fully paid by `other`
    assert edit_payment(client, project["id"], payment["id"], addition_id=999999).status_code == 404


def test_edit_payment_of_other_project_is_not_found(client: TestClient, owner: dict) -> None:
    first = make_project(client, owner["id"])
    second = make_project(client, owner["id"], name="Other")
    addition = make_addition(client, first["id"])
    project_payment = pay(client, first["id"], 100).json()
    addition_payment = pay(client, first["id"], 100, addition["id"]).json()
    assert edit_payment(client, second["id"], project_payment["id"]).status_code == 404
    assert edit_payment(client, second["id"], addition_payment["id"]).status_code == 404
    assert edit_payment(client, first["id"], 999999).status_code == 404
    # Nor can a payment be moved onto another project's addition.
    other_addition = make_addition(client, second["id"])
    response = edit_payment(
        client, first["id"], project_payment["id"], addition_id=other_addition["id"]
    )
    assert response.status_code == 404


def test_lowering_final_payment_reopens_project(client: TestClient, owner: dict) -> None:
    project = make_project(client, owner["id"], price=3001, delivered_on=str(TODAY))
    pay(client, project["id"], 1501)
    final = pay(client, project["id"], 1500).json()
    assert final["kind"] == "final"
    assert get(client, project["id"])["status"] == "done"

    edit_payment(client, project["id"], final["id"], amount=1000)
    project = get(client, project["id"])
    assert project["status"] == "final_payment_due"
    assert (project["outstanding"], project["deposit_due"], project["final_due"]) == (500, 0, 500)
    assert project["total_outstanding"] == 500

    edit_payment(client, project["id"], final["id"], amount=1500)
    assert get(client, project["id"])["status"] == "done"
