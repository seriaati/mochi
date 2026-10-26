"""Tests run against a separate database, `freelance_test`, which is created and
migrated on first use. Each test runs inside a transaction that is rolled back."""

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://freelance:freelance@localhost:5433/freelance_test"
)
assert (make_url(TEST_DATABASE_URL).database or "").endswith("_test"), (
    "refusing to test against a non-test DB"
)
# Point the app (and Alembic) at the test database before anything imports app.config.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
# CORS is set up when the app is created, so its allowed origin is fixed here.
FRONTEND_ORIGIN = "https://dash.example.com"
os.environ["FRONTEND_ORIGIN"] = FRONTEND_ORIGIN

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import auth, discord, keni  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import engine, get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AuthSession  # noqa: E402
from app.passwords import fingerprint, hash_password  # noqa: E402
from app.routers import auth as auth_router  # noqa: E402

TEST_PASSWORD = "correct horse battery staple"
# Cheap scrypt parameters keep the tests fast; the hash says which ones it used.
TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD, n=2**10)


@pytest.fixture(scope="session", autouse=True)
def _test_database() -> None:
    url = make_url(TEST_DATABASE_URL)
    server = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with server.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    server.dispose()
    command.upgrade(Config(Path(__file__).parents[1] / "alembic.ini"), "head")


@pytest.fixture
def session() -> Iterator[Session]:
    """A session whose commits only release savepoints; everything is rolled back after the test."""
    with engine.connect() as conn, conn.begin() as outer:
        with Session(bind=conn, join_transaction_mode="create_savepoint") as session:
            yield session
        outer.rollback()


@pytest.fixture
def anon_client(session: Session) -> Iterator[TestClient]:
    """A client without a session."""
    # Not used as a context manager, so the app lifespan (the reminder loop) never starts.
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client(session: Session, anon_client: TestClient) -> TestClient:
    """A logged-in client, whose session never expires however the test sets the clock."""
    token = "test-session-token"
    session.add(
        AuthSession(
            token_hash=auth.token_hash(token),
            password_fingerprint=fingerprint(TEST_PASSWORD_HASH),
            created_at=datetime(2000, 1, 1, tzinfo=UTC),
            expires_at=datetime(9999, 1, 1, tzinfo=UTC),
            last_seen=datetime(2000, 1, 1, tzinfo=UTC),
        )
    )
    session.flush()
    return TestClient(app, cookies={auth.COOKIE_NAME: token})


@pytest.fixture(autouse=True)
def _auth_config(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The test password and default cookie settings, whatever .env says, with login
    throttling reset and no delay after a wrong password."""
    monkeypatch.setattr(settings, "auth_password_hash", SecretStr(TEST_PASSWORD_HASH))
    monkeypatch.setattr(settings, "cookie_domain", None)
    monkeypatch.setattr(settings, "cookie_secure", True)
    monkeypatch.setattr(auth_router, "FAILED_LOGIN_DELAY", 0)
    auth_router.login_limiter.reset()
    yield
    auth_router.login_limiter.reset()


@pytest.fixture(autouse=True)
def _no_discord(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reminders and profile sync are off, with no ENCRYPTION_KEY, and nothing can reach
    Discord, whatever .env says. Tests that need a webhook or lookups swap in fakes."""
    monkeypatch.setattr(discord, "config", discord.Config())
    monkeypatch.setattr(settings, "encryption_key", None)

    def refuse(*args: object) -> None:
        raise AssertionError("tests must not reach Discord")

    monkeypatch.setattr(discord, "post", refuse)
    monkeypatch.setattr(discord, "fetch_user", refuse)
    monkeypatch.setattr(discord.httpx, "get", refuse)
    monkeypatch.setattr(discord.httpx, "post", refuse)


@pytest.fixture(autouse=True)
def _no_keni(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing can reach Keni. Tests that sync swap in a fake one."""

    def refuse(*args: object) -> None:
        raise AssertionError("tests must not reach Keni")

    monkeypatch.setattr(keni, "_request", refuse)
