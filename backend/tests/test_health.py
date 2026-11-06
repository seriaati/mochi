from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db import get_session
from app.main import app
from tests.conftest import FRONTEND_ORIGIN


def test_health(anon_client: TestClient) -> None:
    response = anon_client.get("/api/health")
    assert response.status_code == 200
    # "web" is the web app the Android app loads when given the API's address.
    assert response.json() == {"status": "ok", "app": "mochi", "web": FRONTEND_ORIGIN}


def test_health_reports_unreachable_database(anon_client: TestClient) -> None:
    class BrokenSession:
        def execute(self, *_: object) -> None:
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    app.dependency_overrides[get_session] = BrokenSession
    response = anon_client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "unreachable"}
