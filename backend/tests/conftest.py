"""Tests run against a separate database, `freelance_test`, which is created and
migrated on first use. Each test runs inside a transaction that is rolled back."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://freelance:freelance@localhost:5433/freelance_test"
)
assert make_url(TEST_DATABASE_URL).database.endswith("_test"), (
    "refusing to test against a non-test DB"
)
# Point the app (and Alembic) at the test database before anything imports app.config.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import discord  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import engine, get_session  # noqa: E402
from app.main import app  # noqa: E402


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
def client(session: Session) -> Iterator[TestClient]:
    # Not used as a context manager, so the app lifespan (the reminder loop) never starts.
    app.dependency_overrides[get_session] = lambda: session
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _no_discord(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reminders and profile sync are off and nothing can reach Discord, whatever .env says.
    Tests that need a webhook or lookups swap in fakes."""
    monkeypatch.setattr(settings, "discord_webhook_url", None)
    monkeypatch.setattr(settings, "discord_mention_user_id", None)
    monkeypatch.setattr(settings, "discord_bot_token", None)

    def refuse(*args: object) -> None:
        raise AssertionError("tests must not reach Discord")

    monkeypatch.setattr(discord, "post", refuse)
    monkeypatch.setattr(discord, "fetch_user", refuse)
    monkeypatch.setattr(discord.httpx, "get", refuse)
    monkeypatch.setattr(discord.httpx, "post", refuse)
