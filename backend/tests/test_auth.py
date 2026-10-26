import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth, passwords
from app.auth import COOKIE_NAME, SESSION_LIFETIME
from app.clock import get_now
from app.config import settings
from app.main import app
from app.models import AuthSession
from app.routers import auth as auth_router
from app.throttle import Limiter
from tests.conftest import FRONTEND_ORIGIN, TEST_PASSWORD

T0 = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
PUBLIC = {
    ("GET", "/api/health"),
    ("GET", "/api/auth/session"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
}


class Now:
    """The time the app sees; tests move it along."""

    def __init__(self) -> None:
        self.value = T0

    def advance(self, delta: timedelta) -> None:
        self.value += delta


@pytest.fixture
def now(anon_client: TestClient) -> Iterator[Now]:
    clock = Now()
    app.dependency_overrides[get_now] = lambda: clock.value
    yield clock
    app.dependency_overrides.pop(get_now, None)


@pytest.fixture
def browser(anon_client: TestClient) -> TestClient:
    """An anonymous client on HTTPS, so it sends Secure cookies back like a browser."""
    return TestClient(app, base_url="https://testserver")


def login(client: TestClient, password: str = TEST_PASSWORD, headers: dict[str, str] | None = None):
    return client.post("/api/auth/login", json={"password": password}, headers=headers)


def logged_in(client: TestClient) -> bool:
    return client.get("/api/auth/session").json()["authenticated"]


def set_cookie_header(response) -> str:
    [header] = [h for h in response.headers.get_list("set-cookie") if h.startswith(COOKIE_NAME)]
    return header


def cookie_attributes(header: str) -> dict[str, str]:
    """Set-Cookie attributes after the name=value pair, lower-cased names to values."""
    attributes = {}
    for part in header.split(";")[1:]:
        name, _, value = part.strip().partition("=")
        attributes[name.lower()] = value
    return attributes


# Passwords


def test_hash_round_trip() -> None:
    encoded = passwords.hash_password("hunter2")
    assert re.fullmatch(r"scrypt\$32768\$8\$1\$[\w-]{22}\$[\w-]{43}", encoded)
    assert passwords.verify_password("hunter2", encoded)
    assert not passwords.verify_password("hunter3", encoded)
    assert not passwords.verify_password("", encoded)


def test_hash_is_salted_and_keeps_its_parameters() -> None:
    cheap = passwords.hash_password("hunter2", n=2**10, r=4, p=2)
    assert cheap.startswith("scrypt$1024$4$2$")
    assert passwords.verify_password("hunter2", cheap)
    assert passwords.hash_password("hunter2") != passwords.hash_password("hunter2")


def test_cli_prints_a_hash_that_verifies(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(passwords, "getpass", lambda prompt: "s3cret pass")
    passwords.main(["hash-password"])
    printed = capsys.readouterr().out.strip()
    assert passwords.verify_password("s3cret pass", printed)
    settings.model_validate({"auth_password_hash": printed})  # accepted by the config


def test_config_rejects_a_plain_password() -> None:
    with pytest.raises(ValueError, match="scrypt"):
        type(settings).model_validate({"auth_password_hash": "hunter2"})


# Logging in


def test_login_and_session(browser: TestClient) -> None:
    assert not logged_in(browser)
    assert browser.get("/api/clients").status_code == 401

    response = login(browser)
    assert response.status_code == 200
    assert response.json() == {"authenticated": True}
    assert logged_in(browser)
    assert browser.get("/api/clients").status_code == 200


def test_wrong_password(browser: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    delays = []
    monkeypatch.setattr(auth_router, "FAILED_LOGIN_DELAY", 0.5)
    monkeypatch.setattr(auth_router.time, "sleep", delays.append)
    response = login(browser, "wrong")
    assert response.status_code == 401
    assert response.json()["detail"] == "Wrong password."
    assert "set-cookie" not in response.headers
    assert delays == [0.5]
    assert not logged_in(browser)


def test_no_password_configured_means_no_login(
    client: TestClient, browser: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "auth_password_hash", None)
    response = login(browser)
    assert response.status_code == 503
    assert "AUTH_PASSWORD_HASH" in response.json()["detail"]
    assert "set-cookie" not in response.headers
    # Existing sessions stop working too.
    assert client.get("/api/clients").status_code == 401


def test_cookie_flags(browser: TestClient) -> None:
    header = set_cookie_header(login(browser))
    attributes = cookie_attributes(header)
    assert attributes["max-age"] == str(int(SESSION_LIFETIME.total_seconds()))
    assert attributes["path"] == "/"
    assert attributes["samesite"].lower() == "lax"
    assert "httponly" in attributes
    assert "secure" in attributes
    assert "domain" not in attributes  # host-only


def test_cookie_flags_follow_config(browser: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cookie_domain", ".example.com")
    monkeypatch.setattr(settings, "cookie_secure", False)
    attributes = cookie_attributes(set_cookie_header(login(browser)))
    assert attributes["domain"] == ".example.com"
    assert "secure" not in attributes
    assert "httponly" in attributes


def test_token_is_stored_only_as_a_hash(browser: TestClient, session: Session) -> None:
    token = login(browser).cookies[COOKIE_NAME]
    assert len(token) >= 43  # 32 random bytes
    row = session.scalars(select(AuthSession)).one()
    assert row.token_hash == auth.token_hash(token)
    stored = [str(getattr(row, c.key)) for c in AuthSession.__table__.columns]
    assert not any(token in value for value in stored)


# Session lifetime


def test_session_expires(browser: TestClient, now: Now, session: Session) -> None:
    login(browser)
    now.advance(SESSION_LIFETIME - timedelta(seconds=1))
    assert logged_in(browser)
    # That use slid the expiry forward a full lifetime.
    now.advance(SESSION_LIFETIME - timedelta(seconds=1))
    assert logged_in(browser)
    now.advance(SESSION_LIFETIME)
    assert not logged_in(browser)
    assert session.scalars(select(AuthSession)).all() == []


def test_sliding_refresh(browser: TestClient, now: Now, session: Session) -> None:
    login(browser)
    row = session.scalars(select(AuthSession)).one()
    assert row.expires_at == T0 + SESSION_LIFETIME

    # Within a day of the last refresh: only last_seen moves, and no cookie is re-sent.
    now.advance(timedelta(hours=1))
    response = browser.get("/api/clients")
    assert response.status_code == 200
    assert "set-cookie" not in response.headers
    session.refresh(row)
    assert row.last_seen == T0 + timedelta(hours=1)
    assert row.expires_at == T0 + SESSION_LIFETIME

    # Later: the expiry slides to a full lifetime from now and the cookie is re-sent with it.
    now.advance(timedelta(days=10))
    response = browser.get("/api/clients")
    assert response.status_code == 200
    assert cookie_attributes(set_cookie_header(response))["max-age"] == str(
        int(SESSION_LIFETIME.total_seconds())
    )
    session.refresh(row)
    assert row.expires_at == now.value + SESSION_LIFETIME
    assert row.created_at == T0


def test_logout(browser: TestClient, session: Session) -> None:
    token = login(browser).cookies[COOKIE_NAME]
    response = browser.post("/api/auth/logout")
    assert response.status_code == 204
    attributes = cookie_attributes(set_cookie_header(response))
    assert attributes["max-age"] == "0"
    assert session.scalars(select(AuthSession)).all() == []
    assert not logged_in(browser)
    # The old token is dead even if the browser kept it.
    stale = TestClient(app, base_url="https://testserver", cookies={COOKIE_NAME: token})
    assert stale.get("/api/clients").status_code == 401


def test_logout_without_a_session(anon_client: TestClient) -> None:
    assert anon_client.post("/api/auth/logout").status_code == 204


def test_new_password_ends_sessions(
    browser: TestClient, monkeypatch: pytest.MonkeyPatch, session: Session
) -> None:
    login(browser)
    assert logged_in(browser)
    new_hash = passwords.hash_password("a new password", n=2**10)
    monkeypatch.setattr(settings, "auth_password_hash", SecretStr(new_hash))
    assert not logged_in(browser)
    assert session.scalars(select(AuthSession)).all() == []
    assert login(browser).status_code == 401
    assert login(browser, "a new password").status_code == 200
    assert logged_in(browser)


# Which routes need a session


def _api_routes() -> list[tuple[str, str]]:
    """Every API route as (method, path). Read from the OpenAPI schema: in this FastAPI,
    app.routes holds included routers as opaque entries rather than their routes."""
    return [
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        if path.startswith("/api")
        for method in operations
    ]


def test_every_other_route_needs_a_session(anon_client: TestClient) -> None:
    protected = [(m, p) for m, p in _api_routes() if (m, p) not in PUBLIC]
    assert len(protected) > 20
    for method, path in protected:
        url = re.sub(r"\{\w+\}", "1", path)
        response = anon_client.request(method, url)
        assert response.status_code == 401, f"{method} {path} answered {response.status_code}"
        assert response.json() == {"detail": "Not logged in."}


def test_public_routes(anon_client: TestClient) -> None:
    assert PUBLIC <= set(_api_routes())
    assert anon_client.get("/api/health").status_code == 200
    assert anon_client.get("/api/auth/session").json() == {"authenticated": False}
    assert login(anon_client, "wrong").json() == {"detail": "Wrong password."}
    assert anon_client.post("/api/auth/logout").status_code == 204


# CSRF and CORS


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://evil.example.net"},
        {"Origin": "null"},
        {"Origin": "http://dash.example.com"},  # wrong scheme
        {"Referer": "https://evil.example.net/page"},
        {"Referer": "not a url"},
    ],
)
def test_csrf_refuses_other_origins(client: TestClient, headers: dict[str, str]) -> None:
    response = client.post("/api/clients", json={"name": "Northwind"}, headers=headers)
    assert response.status_code == 403
    assert response.json() == {"detail": "Cross-site request refused."}
    assert client.get("/api/clients").json() == []
    assert client.delete("/api/clients/1", headers=headers).status_code == 403


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": FRONTEND_ORIGIN},
        {"Origin": "http://testserver"},  # the API's own origin
        {"Referer": f"{FRONTEND_ORIGIN}/clients"},
    ],
)
def test_csrf_allows_known_origins(client: TestClient, headers: dict[str, str]) -> None:
    response = client.post("/api/clients", json={"name": "Northwind"}, headers=headers)
    assert response.status_code == 201


def test_csrf_leaves_reads_alone(client: TestClient) -> None:
    response = client.get("/api/clients", headers={"Origin": "https://evil.example.net"})
    assert response.status_code == 200


def test_csrf_covers_login(browser: TestClient) -> None:
    response = login(browser, headers={"Origin": "https://evil.example.net"})
    assert response.status_code == 403
    assert "set-cookie" not in response.headers


def test_csrf_reads_frontend_origins_from_config(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        settings, "frontend_origin", "https://a.example.com, https://b.example.com/"
    )
    headers = {"Origin": "https://b.example.com"}
    assert client.post("/api/clients", json={"name": "N"}, headers=headers).status_code == 201
    headers = {"Origin": FRONTEND_ORIGIN}
    assert client.post("/api/clients", json={"name": "N"}, headers=headers).status_code == 403


def test_cors_preflight_from_the_frontend(anon_client: TestClient) -> None:
    response = anon_client.options(
        "/api/clients",
        headers={
            "Origin": FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "POST" in response.headers["access-control-allow-methods"]


def test_cors_refuses_other_origins(anon_client: TestClient) -> None:
    response = anon_client.options(
        "/api/clients",
        headers={"Origin": "https://evil.example.net", "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_cors_headers_on_credentialed_requests(browser: TestClient) -> None:
    response = login(browser, headers={"Origin": FRONTEND_ORIGIN})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"


# Throttling


def test_login_throttled_per_ip(anon_client: TestClient) -> None:
    for _ in range(5):
        assert login(anon_client, "wrong").status_code == 401
    response = login(anon_client)  # even the right password waits
    assert response.status_code == 429
    assert 1 <= int(response.headers["retry-after"]) <= 60
    assert "Too many login attempts" in response.json()["detail"]
    # Another address is still let through.
    elsewhere = TestClient(app, client=("203.0.113.9", 50000))
    assert login(elsewhere).status_code == 200


def test_login_throttled_overall(anon_client: TestClient) -> None:
    for i in range(30):
        attacker = TestClient(app, client=(f"198.51.100.{i}", 50000))
        assert login(attacker, "wrong").status_code == 401
    response = login(TestClient(app, client=("203.0.113.9", 50000)))
    assert response.status_code == 429
    assert "retry-after" in response.headers


def test_login_throttle_window_passes(
    anon_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [1000.0]
    monkeypatch.setattr(auth_router.login_limiter, "clock", lambda: clock[0])
    for _ in range(5):
        login(anon_client, "wrong")
    clock[0] += 45
    response = login(anon_client)
    assert response.status_code == 429
    assert response.headers["retry-after"] == "15"
    clock[0] += 15
    assert login(anon_client).status_code == 200


def test_limiter_retry_after() -> None:
    clock = [0.0]
    limiter = Limiter(per_key=2, total=3, window=60, clock=lambda: clock[0])
    assert limiter.hit("a") is None
    clock[0] = 10.5
    assert limiter.hit("a") is None
    assert limiter.hit("a") == 50  # until the first attempt leaves the window
    assert limiter.hit("b") is None
    assert limiter.hit("c") == 50  # the overall cap
    clock[0] = 60
    assert limiter.hit("c") is None
    limiter.reset()
    assert limiter.hit("a") is None
