"""Discord profile sync: parsing users, storing lookups, the TTL refresh and what the API shows.

Lookups go to a fake Discord (or a fake httpx.get for the request itself), never the real one.
The clock is pinned to 23 October 2026, 10:00 in Asia/Taipei."""

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy.orm import Session

from app import crypto, discord, discord_sync
from app.clock import get_now
from app.config import settings
from app.main import app
from app.models import AppSettings, Client, ContactKind, ContactMethod, SyncStatus

REAL_FETCH = discord.fetch_user  # before conftest swaps it out
NOW = datetime(2026, 10, 23, 2, 0, tzinfo=UTC)
TOKEN = "bot-token-that-must-stay-secret"
DAN = 175928847299117063  # default avatar index (id >> 22) % 6 == 2
SORA = 80351110224678912  # index 5
ME = 396892407884546058
CDN = "https://cdn.discordapp.com"


def user(user_id: int, username: str, global_name: str | None = None, avatar: str | None = None):
    return discord.User(username, global_name, discord.avatar_url(user_id, avatar))


class FakeDiscord:
    """Answers lookups from `users` (a missing ID is an unknown user) and records each one."""

    def __init__(self) -> None:
        self.users: dict[int, discord.User | Exception] = {
            DAN: user(DAN, "danpark", "Daniel", "abc123"),
            SORA: user(SORA, "sora.px"),
            ME: user(ME, "seria", "Seria"),
        }
        self.calls: list[tuple[int, float]] = []

    def __call__(self, user_id: int, timeout: float) -> discord.User | None:
        self.calls.append((user_id, timeout))
        answer = self.users.get(user_id)
        if isinstance(answer, Exception):
            raise answer
        return answer

    @property
    def ids(self) -> list[int]:
        return [user_id for user_id, _ in self.calls]


@pytest.fixture(autouse=True)
def _pinned() -> Iterator[None]:
    app.dependency_overrides[get_now] = lambda: NOW
    yield
    app.dependency_overrides.pop(get_now, None)


@pytest.fixture(autouse=True)
def _not_paused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discord_sync, "_paused_until", None)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeDiscord:
    """Turns sync on with a bot token and swaps in the fake Discord."""
    fake = FakeDiscord()
    monkeypatch.setattr(discord, "config", replace(discord.config, bot_token=SecretStr(TOKEN)))
    monkeypatch.setattr(discord, "fetch_user", fake)
    return fake


def add_client(client: TestClient, name: str = "Northwind Coffee") -> dict:
    response = client.post("/api/clients", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def add_contact(client: TestClient, owner: dict, user_id: int | None, value: str = "@dan") -> dict:
    body = {"kind": "discord", "value": value, "discord_user_id": str(user_id) if user_id else None}
    response = client.post(f"/api/clients/{owner['id']}/contacts", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def get_client(client: TestClient, owner: dict) -> dict:
    return client.get(f"/api/clients/{owner['id']}").json()


# Parsing


def test_avatar_urls() -> None:
    assert discord.avatar_url(DAN, "abc123") == f"{CDN}/avatars/{DAN}/abc123.png?size=128"
    assert (
        discord.avatar_url(DAN, "a_abc123")
        == f"{CDN}/avatars/{DAN}/a_abc123.webp?size=128&animated=true"
    )
    # No avatar: Discord's default, picked from the ID, or from the old #1234 tag.
    assert discord.avatar_url(DAN, None) == f"{CDN}/embed/avatars/2.png"
    assert discord.avatar_url(SORA, None, "0") == f"{CDN}/embed/avatars/5.png"
    assert discord.avatar_url(SORA, None, "1337") == f"{CDN}/embed/avatars/2.png"


def test_parse_user() -> None:
    parsed = discord.parse_user(
        {"id": str(DAN), "username": "danpark", "global_name": None, "avatar": None}
    )
    assert parsed == discord.User("danpark", None, f"{CDN}/embed/avatars/2.png")

    animated = discord.parse_user(
        {"id": str(DAN), "username": "danpark", "global_name": "Daniel", "avatar": "a_ff"}
    )
    assert animated.global_name == "Daniel"
    assert animated.avatar_url.endswith(f"/avatars/{DAN}/a_ff.webp?size=128&animated=true")


def fake_get(monkeypatch: pytest.MonkeyPatch, response: httpx.Response) -> list[dict]:
    monkeypatch.setattr(discord, "fetch_user", REAL_FETCH)
    monkeypatch.setattr(discord, "config", replace(discord.config, bot_token=SecretStr(TOKEN)))
    monkeypatch.setattr(settings, "discord_api_base", "http://discord.test/api/v10")
    requests: list[dict] = []

    def get(url: str, **kwargs: object) -> httpx.Response:
        requests.append({"url": url, **kwargs})
        response.request = httpx.Request("GET", url)
        return response

    monkeypatch.setattr(discord.httpx, "get", get)
    return requests


def test_fetch_user_request(monkeypatch: pytest.MonkeyPatch) -> None:
    body = {"id": str(DAN), "username": "danpark", "global_name": "Daniel", "avatar": "abc"}
    requests = fake_get(monkeypatch, httpx.Response(200, json=body))
    assert discord.fetch_user(DAN, 3) == discord.User(
        "danpark", "Daniel", f"{CDN}/avatars/{DAN}/abc.png?size=128"
    )
    assert requests == [
        {
            "url": f"http://discord.test/api/v10/users/{DAN}",
            "headers": {"Authorization": f"Bot {TOKEN}"},
            "timeout": 3,
        }
    ]


def test_fetch_unknown_user(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_get(monkeypatch, httpx.Response(404, json={"message": "Unknown User", "code": 10013}))
    assert discord.fetch_user(DAN, 3) is None


def test_fetch_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_get(monkeypatch, httpx.Response(429, json={"retry_after": 2.5, "global": False}))
    with pytest.raises(discord.RateLimited) as limited:
        discord.fetch_user(DAN, 3)
    assert limited.value.retry_after == 2.5

    fake_get(monkeypatch, httpx.Response(429, headers={"Retry-After": "7"}, text="slow down"))
    with pytest.raises(discord.RateLimited) as limited:
        discord.fetch_user(DAN, 3)
    assert limited.value.retry_after == 7


def test_fetch_errors_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_get(monkeypatch, httpx.Response(500))
    with pytest.raises(httpx.HTTPError):
        discord.fetch_user(DAN, 3)


# Sync on save


def test_sync_on_create(client: TestClient, fake: FakeDiscord) -> None:
    owner = add_client(client)
    contact = add_contact(client, owner, DAN)
    assert fake.calls == [(DAN, discord_sync.SAVE_TIMEOUT)]
    assert contact["value"] == "@dan"  # the typed handle stays as a fallback
    assert contact["discord_profile"] == {
        "status": "ok",
        "synced_at": "2026-10-23T02:00:00Z",
        "username": "danpark",
        "display_name": "Daniel",
        "avatar_url": f"{CDN}/avatars/{DAN}/abc123.png?size=128",
    }
    fetched = get_client(client, owner)
    assert fetched["contacts"][0] == contact
    assert fetched["avatar_url"] == f"{CDN}/avatars/{DAN}/abc123.png?size=128"
    assert fetched["discord_name"] == "Daniel"


def test_display_name_falls_back_to_username(client: TestClient, fake: FakeDiscord) -> None:
    profile = add_contact(client, add_client(client), SORA)["discord_profile"]
    assert profile["display_name"] == "sora.px"
    assert profile["avatar_url"] == f"{CDN}/embed/avatars/5.png"


def test_add_client_by_discord_id(client: TestClient, fake: FakeDiscord) -> None:
    response = client.post("/api/clients", json={"name": "", "discord_user_id": str(DAN)})
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["name"] == "Daniel"  # their display name
    assert created["discord_name"] == "Daniel"
    [contact] = created["contacts"]
    assert contact["kind"] == "discord"
    assert contact["value"] == "danpark"
    assert contact["discord_user_id"] == str(DAN)
    assert contact["discord_profile"]["status"] == "ok"
    assert fake.calls == [(DAN, discord_sync.SAVE_TIMEOUT)]

    # Without a display name, the username; a typed name wins.
    sora = client.post("/api/clients", json={"discord_user_id": str(SORA)}).json()
    assert sora["name"] == "sora.px"
    named = client.post("/api/clients", json={"name": "Northwind", "discord_user_id": str(DAN)})
    assert named.json()["name"] == "Northwind"


def test_add_client_by_unknown_discord_id(client: TestClient, fake: FakeDiscord) -> None:
    body = {"name": "Northwind", "discord_user_id": "99999999999999999"}
    response = client.post("/api/clients", json=body)
    assert response.status_code == 422
    assert response.json()["detail"] == "No Discord user has that ID"
    assert client.get("/api/clients").json() == []


def test_add_client_by_discord_id_without_a_lookup(client: TestClient, fake: FakeDiscord) -> None:
    fake.users[DAN] = httpx.ConnectError("down")
    failed = client.post("/api/clients", json={"discord_user_id": str(DAN)})
    assert failed.status_code == 422
    assert (
        failed.json()["detail"] == "Couldn't look that Discord user up. Try again, or enter a name"
    )

    # With a name it's added anyway; the handle is the ID until a lookup works.
    named = client.post("/api/clients", json={"name": "Northwind", "discord_user_id": str(DAN)})
    assert named.status_code == 201
    assert named.json()["contacts"][0]["value"] == str(DAN)
    assert named.json()["contacts"][0]["discord_profile"]["status"] == "error"


def test_add_client_by_discord_id_with_sync_off(client: TestClient) -> None:
    response = client.post("/api/clients", json={"discord_user_id": str(DAN)})
    assert response.status_code == 422
    assert response.json()["detail"].startswith("Discord sync is off")


def test_add_client_needs_a_name_or_discord_id(client: TestClient) -> None:
    assert client.post("/api/clients", json={"name": " "}).status_code == 422


def test_edit_client_discord_id(client: TestClient, fake: FakeDiscord) -> None:
    owner = add_client(client)
    url = f"/api/clients/{owner['id']}"
    body = {"name": "Northwind"}

    # Left out, contacts stay as they are; sent, it adds a Discord contact.
    assert client.put(url, json=body).json()["contacts"] == []
    added = client.put(url, json=body | {"discord_user_id": str(DAN)}).json()
    [contact] = added["contacts"]
    assert (contact["value"], contact["discord_user_id"]) == ("danpark", str(DAN))

    # A new ID goes on that contact and is looked up; an unchanged one isn't.
    moved = client.put(url, json=body | {"discord_user_id": str(SORA)}).json()
    [contact] = moved["contacts"]
    assert (contact["value"], contact["discord_user_id"]) == ("sora.px", str(SORA))
    client.put(url, json=body | {"discord_user_id": str(SORA)})
    assert fake.ids == [DAN, SORA]

    # Null takes the ID off and keeps the handle.
    cleared = client.put(url, json=body | {"discord_user_id": None}).json()
    [contact] = cleared["contacts"]
    assert (contact["value"], contact["discord_user_id"]) == ("sora.px", None)


def test_edit_client_discord_id_prefers_the_linked_contact(
    client: TestClient, fake: FakeDiscord
) -> None:
    owner = add_client(client)
    add_contact(client, owner, None, value="@old")
    linked = add_contact(client, owner, DAN)
    body = {"name": "Northwind", "discord_user_id": str(SORA)}
    response = client.put(f"/api/clients/{owner['id']}", json=body)
    contacts = {c["id"]: c for c in response.json()["contacts"]}
    assert len(contacts) == 2
    assert contacts[linked["id"]]["discord_user_id"] == str(SORA)


def test_edit_client_discord_id_without_a_lookup(client: TestClient) -> None:
    owner = client.post("/api/clients", json={"name": "N", "discord_user_id": str(DAN)}).json()
    assert owner["contacts"][0]["value"] == str(DAN)  # sync is off, so the handle is the ID
    body = {"name": "N", "discord_user_id": str(SORA)}
    edited = client.put(f"/api/clients/{owner['id']}", json=body).json()
    assert edited["contacts"][0]["value"] == str(SORA)  # and follows it


def test_edit_client_unknown_discord_id(client: TestClient, fake: FakeDiscord) -> None:
    owner = add_client(client)
    body = {"name": "Renamed", "discord_user_id": "99999999999999999"}
    response = client.put(f"/api/clients/{owner['id']}", json=body)
    assert response.status_code == 422
    assert response.json()["detail"] == "No Discord user has that ID"
    assert get_client(client, owner)["name"] == "Northwind Coffee"  # nothing saved


def test_sync_when_the_id_changes(client: TestClient, fake: FakeDiscord) -> None:
    owner = add_client(client)
    contact = add_contact(client, owner, DAN)
    url = f"/api/clients/{owner['id']}/contacts/{contact['id']}"

    same = client.put(url, json={"kind": "discord", "value": "@dp", "discord_user_id": str(DAN)})
    assert same.json()["discord_profile"]["username"] == "danpark"
    assert fake.ids == [DAN]  # an unchanged ID isn't looked up again

    moved = client.put(url, json={"kind": "discord", "value": "@dp", "discord_user_id": str(SORA)})
    assert moved.json()["discord_profile"]["username"] == "sora.px"
    assert fake.ids == [DAN, SORA]

    removed = client.put(url, json={"kind": "discord", "value": "@dp"}).json()
    assert removed["discord_profile"] is None
    assert get_client(client, owner)["avatar_url"] is None
    assert fake.ids == [DAN, SORA]


def test_unknown_user(client: TestClient, fake: FakeDiscord, session: Session) -> None:
    owner = add_client(client)
    contact = add_contact(client, owner, 99999999999999999)
    assert contact["discord_profile"]["status"] == "not_found"
    assert contact["discord_profile"]["avatar_url"] is None
    assert get_client(client, owner)["avatar_url"] is None

    # A user that disappears loses the old profile.
    row = session.get_one(ContactMethod, add_contact(client, owner, DAN)["id"])
    del fake.users[DAN]
    discord_sync.sync_now([row], NOW)
    assert row.discord_sync_status == SyncStatus.NOT_FOUND
    assert row.discord_username is None


def test_failed_lookup_keeps_the_last_profile(
    client: TestClient, fake: FakeDiscord, session: Session
) -> None:
    owner = add_client(client)
    row = session.get_one(ContactMethod, add_contact(client, owner, DAN)["id"])
    fake.users[DAN] = httpx.ConnectTimeout("timed out")
    discord_sync.sync_now([row], NOW + timedelta(hours=2))
    profile = get_client(client, owner)["contacts"][0]["discord_profile"]
    assert profile["status"] == "error"
    assert profile["username"] == "danpark"
    assert profile["synced_at"] == "2026-10-23T04:00:00Z"


def test_save_while_rate_limited(client: TestClient, fake: FakeDiscord) -> None:
    fake.users[DAN] = discord.RateLimited(30)
    contact = add_contact(client, add_client(client), DAN)
    assert contact["discord_profile"]["status"] == "pending"  # the loop looks it up later


# The background refresh


def contact_row(
    session: Session,
    user_id: int,
    synced_ago: timedelta | None,
    status: SyncStatus | None = SyncStatus.OK,
) -> ContactMethod:
    owner = Client(name=f"Client {user_id}")
    row = ContactMethod(
        client=owner,
        kind=ContactKind.DISCORD,
        value="@x",
        discord_user_id=user_id,
        discord_sync_status=status if synced_ago is not None else None,
        discord_synced_at=NOW - synced_ago if synced_ago is not None else None,
    )
    session.add(row)
    session.flush()
    return row


def test_refresh_picks_only_stale_profiles(fake: FakeDiscord, session: Session) -> None:
    never = contact_row(session, 10**17 + 1, None)
    old = contact_row(session, 10**17 + 2, timedelta(hours=1, minutes=1))
    fresh = contact_row(session, 10**17 + 3, timedelta(minutes=59))
    failed = contact_row(session, 10**17 + 4, timedelta(minutes=6), SyncStatus.ERROR)
    just_failed = contact_row(session, 10**17 + 5, timedelta(minutes=4), SyncStatus.ERROR)
    missing = contact_row(session, 10**17 + 6, timedelta(minutes=30), SyncStatus.NOT_FOUND)
    no_id = ContactMethod(client=never.client, kind=ContactKind.DISCORD, value="@noid")
    session.add(no_id)
    session.flush()

    assert discord_sync.due(session, NOW) == [never, old, failed]  # least recent first
    assert discord_sync.refresh_due(session, NOW) == 3
    assert fake.ids == [never.discord_user_id, old.discord_user_id, failed.discord_user_id]
    assert fresh.discord_synced_at == NOW - timedelta(minutes=59)

    # A minute on: an hour since `fresh` was synced, five since `just_failed` failed.
    assert discord_sync.due(session, NOW + timedelta(minutes=1)) == [fresh, just_failed]
    # What was just looked up stays fresh until the TTL passes again.
    everything = {never, old, fresh, failed, just_failed, missing}
    assert set(discord_sync.due(session, NOW + discord_sync.TTL)) == everything


def test_refresh_is_batched(fake: FakeDiscord, session: Session) -> None:
    for n in range(discord_sync.BATCH + 3):
        contact_row(session, 10**17 + n, None)
    assert discord_sync.refresh_due(session, NOW) == discord_sync.BATCH
    assert discord_sync.refresh_due(session, NOW) == 3
    assert discord_sync.refresh_due(session, NOW) == 0


def test_rate_limit_pauses_lookups(fake: FakeDiscord, session: Session) -> None:
    first = contact_row(session, DAN, None)
    contact_row(session, SORA, None)
    fake.users[DAN] = discord.RateLimited(30)

    assert discord_sync.refresh_due(session, NOW) == 0
    assert fake.ids == [DAN]  # stopped at the 429
    assert discord_sync.refresh_due(session, NOW + timedelta(seconds=29)) == 0
    assert fake.ids == [DAN]  # still waiting out retry_after

    fake.users[DAN] = user(DAN, "danpark")
    assert discord_sync.refresh_due(session, NOW + timedelta(seconds=30)) == 2
    assert first.discord_username == "danpark"


def test_sync_now_while_rate_limited(client: TestClient, fake: FakeDiscord) -> None:
    owner = add_client(client)
    add_contact(client, owner, DAN)
    fake.users[DAN] = discord.RateLimited(12.2)
    response = client.post(f"/api/clients/{owner['id']}/discord/sync")
    assert response.status_code == 429
    assert response.json()["detail"] == "Discord asked to slow down. Try again in 13 s"


def test_sync_now(client: TestClient, fake: FakeDiscord) -> None:
    owner = add_client(client)
    add_contact(client, owner, DAN)
    add_contact(client, owner, SORA, "@sora")
    client.post(f"/api/clients/{owner['id']}/contacts", json={"kind": "email", "value": "a@b.c"})
    fake.users[DAN] = user(DAN, "danpark", "Dan P.", "new")

    response = client.post(f"/api/clients/{owner['id']}/discord/sync")
    assert response.status_code == 200
    assert fake.ids == [DAN, SORA, DAN, SORA]  # on save, then both again, however fresh
    data = response.json()
    assert data["discord_name"] == "Dan P."  # the first synced Discord contact
    assert data["avatar_url"] == f"{CDN}/avatars/{DAN}/new.png?size=128"
    assert client.post("/api/clients/999999/discord/sync").status_code == 404


def test_avatars_on_projects_and_retainers(client: TestClient, fake: FakeDiscord) -> None:
    owner = add_client(client)
    add_contact(client, owner, DAN)
    avatar = f"{CDN}/avatars/{DAN}/abc123.png?size=128"
    project = client.post(
        "/api/projects",
        json={"client_id": owner["id"], "name": "Site", "price": 1000, "started_on": "2026-10-01"},
    ).json()
    assert project["client"]["avatar_url"] == avatar
    retainer = client.post(
        "/api/retainers",
        json={
            "client_id": owner["id"],
            "amount": 250,
            "due_day": 25,
            "collection": "ask",
            "started_on": "2026-10-01",
        },
    ).json()
    assert retainer["client"]["avatar_url"] == avatar
    overview = client.get("/api/maintenance").json()
    assert overview["next_reminder"]["client"]["avatar_url"] == avatar
    assert overview["calendar"][0]["entries"][0]["client"]["avatar_url"] == avatar


# Your own profile


def test_mention_profile(
    client: TestClient, fake: FakeDiscord, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def mention() -> Any:
        return client.get("/api/maintenance").json()["reminders"]["mention"]

    assert mention() is None  # no mention user
    monkeypatch.setattr(discord, "config", replace(discord.config, mention_user_id=str(ME)))
    assert mention()["status"] == "pending"

    contact_row(session, DAN, None)
    assert discord_sync.refresh_due(session, NOW) == 2
    assert fake.ids == [ME, DAN]  # yours first
    assert mention()["display_name"] == "Seria"
    assert session.get_one(AppSettings, 1).discord_user_id == ME
    assert discord_sync.due(session, NOW + timedelta(minutes=59)) == []

    # A new mention ID starts over.
    monkeypatch.setattr(discord, "config", replace(discord.config, mention_user_id=str(SORA)))
    assert mention()["status"] == "pending"
    assert discord_sync.refresh_due(session, NOW + timedelta(minutes=1)) == 1
    assert mention()["display_name"] == "sora.px"


# Sync off


def test_no_token_means_no_lookups(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # conftest leaves the token unset and fails any lookup.
    monkeypatch.setattr(discord, "config", replace(discord.config, mention_user_id=str(ME)))
    owner = add_client(client)
    contact = add_contact(client, owner, DAN)
    off = {"status": "off", "synced_at": None, "username": None, "display_name": None}
    assert contact["discord_profile"] == off | {"avatar_url": None}
    assert discord_sync.refresh_due(session, NOW) == 0
    assert client.get("/api/maintenance").json()["reminders"]["mention"]["status"] == "off"

    response = client.post(f"/api/clients/{owner['id']}/discord/sync")
    assert response.status_code == 409
    assert response.json()["detail"] == "Discord sync is off: add a bot token in Settings first"


def test_cached_profiles_hide_while_sync_is_off(
    client: TestClient, fake: FakeDiscord, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = add_client(client)
    add_contact(client, owner, DAN)
    monkeypatch.setattr(discord, "config", replace(discord.config, bot_token=None))
    fetched = get_client(client, owner)
    assert fetched["avatar_url"] is None
    assert fetched["contacts"][0]["discord_profile"]["status"] == "off"


def test_token_never_in_responses(
    client: TestClient, fake: FakeDiscord, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(discord, "config", replace(discord.config, mention_user_id=str(ME)))
    owner = add_client(client)
    contact = add_contact(client, owner, DAN)
    fake.users[SORA] = httpx.HTTPStatusError(
        f"401 for Bot {TOKEN}", request=httpx.Request("GET", "x"), response=httpx.Response(401)
    )
    add_contact(client, owner, SORA)
    client.post(
        "/api/projects",
        json={"client_id": owner["id"], "name": "Site", "price": 1, "started_on": "2026-10-01"},
    )
    responses = [
        client.get("/api/clients"),
        client.get(f"/api/clients/{owner['id']}"),
        client.post(f"/api/clients/{owner['id']}/discord/sync"),
        client.put(
            f"/api/clients/{owner['id']}/contacts/{contact['id']}",
            json={"kind": "discord", "value": "@d", "discord_user_id": str(SORA)},
        ),
        client.get("/api/projects"),
        client.get("/api/retainers"),
        client.get("/api/maintenance"),
        client.get("/api/settings"),
        client.get("/openapi.json"),
    ]
    for response in responses:
        assert response.status_code == 200, response.text
        assert TOKEN not in response.text
    assert TOKEN not in repr(discord.config)


def test_tick_uses_its_own_session(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []

    def refresh(session: Session, now: datetime, pause: float = 0) -> int:
        calls.append((now.tzinfo, pause))
        return 0

    monkeypatch.setattr(discord_sync, "refresh_due", refresh)
    discord_sync.tick()
    assert calls == [(UTC, discord_sync.PAUSE_SECONDS)]


# The bot token in Settings

KEY = "k" * 32
BOT_TOKEN = "MTk4NjIyNDgzNDcxOTI1MjQ4.Cl2FMQ.ZnCjm1XVW7vRze4b7Cq4se7kKWs"  # Discord docs' example


def test_bot_token_is_stored_encrypted(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "encryption_key", SecretStr(KEY))
    owner = add_client(client)
    add_contact(client, owner, DAN)  # sync is off: no lookup
    response = client.put("/api/settings/discord-bot-token", json={"token": f" {BOT_TOKEN} "})
    assert response.status_code == 200, response.text
    assert response.json()["discord_bot_token_set"] is True
    assert response.json()["encryption_key_set"] is True
    assert BOT_TOKEN not in response.text
    assert BOT_TOKEN not in client.get("/api/settings").text

    stored = session.get_one(AppSettings, 1).discord_bot_token_encrypted
    assert stored is not None and BOT_TOKEN not in stored
    assert crypto.decrypt(stored) == BOT_TOKEN
    assert discord.config.bot_token == SecretStr(BOT_TOKEN)
    assert get_client(client, owner)["contacts"][0]["discord_profile"]["status"] == "pending"

    # Saving the other settings keeps it.
    client.put("/api/settings", json={"timezone": "Asia/Tokyo"})
    assert discord.config.bot_token == SecretStr(BOT_TOKEN)

    # Under a different key it can't be read, so sync is off until it's entered again.
    monkeypatch.setattr(settings, "encryption_key", SecretStr("x" * 32))
    discord.load(session)
    assert discord.config.bot_token is None
    assert get_client(client, owner)["contacts"][0]["discord_profile"]["status"] == "off"

    response = client.delete("/api/settings/discord-bot-token")
    assert response.json()["discord_bot_token_set"] is False
    assert session.get_one(AppSettings, 1).discord_bot_token_encrypted is None


def test_bot_token_needs_an_encryption_key(client: TestClient, session: Session) -> None:
    # conftest leaves ENCRYPTION_KEY unset.
    response = client.put("/api/settings/discord-bot-token", json={"token": BOT_TOKEN})
    assert response.status_code == 409
    assert response.json()["detail"] == "Set ENCRYPTION_KEY on the API before saving a bot token"
    assert session.get_one(AppSettings, 1).discord_bot_token_encrypted is None
    assert client.get("/api/settings").json()["encryption_key_set"] is False


@pytest.mark.parametrize("token", ["", "not a token", "a.b", "a.b.c.d", "a.b.c\nX-Evil: 1"])
def test_bad_bot_tokens_are_rejected(
    client: TestClient, token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "encryption_key", SecretStr(KEY))
    response = client.put("/api/settings/discord-bot-token", json={"token": token})
    assert response.status_code == 422


def test_encryption_key_must_be_long() -> None:
    with pytest.raises(ValidationError):
        type(settings).model_validate({"encryption_key": "too short"})
    assert type(settings).model_validate({"encryption_key": KEY}).encryption_key == SecretStr(KEY)
