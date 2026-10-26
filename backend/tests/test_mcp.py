import asyncio
import base64
import dataclasses
import hashlib
import json
import secrets
from collections.abc import Iterator
from contextlib import nullcontext
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import jsonschema
import pytest
from fastapi.testclient import TestClient
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import mcp_server, oauth, reminders
from app.clock import utc_now
from app.config import settings
from app.main import app
from app.mcp_server import mcp
from app.models import OAuthToken
from app.passwords import hash_password
from tests.conftest import FRONTEND_ORIGIN

REDIRECT_URI = "http://localhost:33418/callback"


@pytest.fixture(autouse=True)
def db(session: Session, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The OAuth provider and the tools open their own sessions; give them the test's."""
    monkeypatch.setattr(oauth, "SessionLocal", lambda: nullcontext(session))
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: nullcontext(session))
    yield
    oauth._requests.clear()


def register(anon_client: TestClient, auth_method: str = "none") -> dict:
    response = anon_client.post(
        "/register",
        json={
            "client_name": "Claude",
            "redirect_uris": [REDIRECT_URI],
            "token_endpoint_auth_method": auth_method,
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@dataclasses.dataclass
class SignIn:
    """A client part-way through signing in: sent to the consent page."""

    client: dict
    verifier: str
    request_id: str

    def token_form(self, **fields: str) -> dict[str, str]:
        form = {"client_id": self.client["client_id"], **fields}
        if secret := self.client.get("client_secret"):
            form["client_secret"] = secret
        return form


def start(anon_client: TestClient, client_info: dict | None = None) -> SignIn:
    client_info = client_info or register(anon_client)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    response = anon_client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": client_info["client_id"],
            "redirect_uri": REDIRECT_URI,
            "code_challenge": challenge.decode(),
            "code_challenge_method": "S256",
            "state": "client-state",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text
    consent = urlsplit(response.headers["location"])
    assert (
        f"{consent.scheme}://{consent.netloc}{consent.path}" == f"{FRONTEND_ORIGIN}/oauth/authorize"
    )
    (request_id,) = parse_qs(consent.query)["request"]
    return SignIn(client_info, verifier, request_id)


def approve(client: TestClient, sign_in: SignIn) -> str:
    response = client.post(f"/api/oauth/requests/{sign_in.request_id}", json={"approve": True})
    assert response.status_code == 200, response.text
    redirect = urlsplit(response.json()["redirect_uri"])
    assert f"{redirect.scheme}://{redirect.netloc}{redirect.path}" == REDIRECT_URI
    query = parse_qs(redirect.query)
    assert query["state"] == ["client-state"]
    return query["code"][0]


def exchange(anon_client: TestClient, sign_in: SignIn, code: str):
    form = sign_in.token_form(
        grant_type="authorization_code",
        code=code,
        redirect_uri=REDIRECT_URI,
        code_verifier=sign_in.verifier,
    )
    return anon_client.post("/token", data=form)


def refresh(anon_client: TestClient, sign_in: SignIn, refresh_token: str):
    form = sign_in.token_form(grant_type="refresh_token", refresh_token=refresh_token)
    return anon_client.post("/token", data=form)


def connect(client: TestClient, anon_client: TestClient, **kwargs: object) -> tuple[SignIn, dict]:
    """Signs a new MCP client in all the way, returning its tokens."""
    sign_in = start(anon_client, **kwargs)
    response = exchange(anon_client, sign_in, approve(client, sign_in))
    assert response.status_code == 200, response.text
    return sign_in, response.json()


def access_works(session: Session, token: str) -> bool:
    return oauth.load_access_token(session, utc_now(), token) is not None


# Discovery


def test_metadata(anon_client: TestClient) -> None:
    resource = anon_client.get("/.well-known/oauth-protected-resource/mcp").json()
    assert resource["resource"] == "http://localhost:8000/mcp"
    assert resource["scopes_supported"] == ["dashboard"]
    server = anon_client.get("/.well-known/oauth-authorization-server").json()
    assert server["authorization_endpoint"] == "http://localhost:8000/authorize"
    assert server["token_endpoint"] == "http://localhost:8000/token"
    assert server["registration_endpoint"] == "http://localhost:8000/register"
    assert server["code_challenge_methods_supported"] == ["S256"]


@pytest.mark.parametrize("authorization", [None, "Bearer not-a-token"])
def test_mcp_needs_a_token(anon_client: TestClient, authorization: str | None) -> None:
    headers = {"Authorization": authorization} if authorization else {}
    response = anon_client.post("/mcp", json={}, headers=headers)
    assert response.status_code == 401
    challenge = response.headers["www-authenticate"]
    assert 'resource_metadata="http://localhost:8000/.well-known/oauth-protected-resource/mcp"' in (
        challenge
    )


def test_api_routes_still_win(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/clients").json() == []


# Signing in


def test_sign_in_and_use_the_tools(
    client: TestClient, anon_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole flow, as Claude does it, then MCP over HTTP. The only test that runs the app's
    lifespan: the MCP session manager starts once per process."""

    async def no_reminders() -> None:
        pass

    monkeypatch.setattr(reminders, "run_forever", no_reminders)
    client_info = register(anon_client, "client_secret_post")
    assert client_info["client_secret"]
    sign_in = start(anon_client, client_info)

    shown = client.get(f"/api/oauth/requests/{sign_in.request_id}").json()
    assert shown == {"client_name": "Claude", "redirect_uri": REDIRECT_URI}
    response = exchange(anon_client, sign_in, approve(client, sign_in))
    assert response.status_code == 200, response.text
    tokens = response.json()
    assert tokens["token_type"] == "Bearer"
    assert tokens["scope"] == "dashboard"
    assert tokens["expires_in"] == 3600

    with TestClient(app) as http:
        headers = {
            "Authorization": f"Bearer {tokens['access_token']}",
            "Accept": "application/json, text/event-stream",
        }

        def rpc(method: str, params: dict, request_id: int | None = 1) -> dict | None:
            message = {"jsonrpc": "2.0", "method": method, "params": params}
            if request_id is not None:
                message["id"] = request_id
            response = http.post("/mcp", json=message, headers=headers)
            assert response.status_code in (200, 202), response.text
            if "mcp-session-id" in response.headers:
                headers["mcp-session-id"] = response.headers["mcp-session-id"]
            data = [line for line in response.text.splitlines() if line.startswith("data: ")]
            return json.loads(data[-1].removeprefix("data: ")) if data else None

        init = rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        )
        assert init["result"]["serverInfo"]["name"] == "Mochi"
        rpc("notifications/initialized", {}, request_id=None)

        tools = rpc("tools/list", {})["result"]["tools"]
        assert {"list_clients", "create_project", "get_maintenance"} <= {t["name"] for t in tools}
        assert all("$ref" not in json.dumps(t["inputSchema"]) for t in tools)

        created = rpc(
            "tools/call", {"name": "create_client", "arguments": {"client": {"name": "Northwind"}}}
        )
        assert created["result"]["structuredContent"]["name"] == "Northwind"
        listed = rpc("tools/call", {"name": "list_clients", "arguments": {}})
        assert [c["name"] for c in listed["result"]["structuredContent"]["result"]] == ["Northwind"]


def test_deny(client: TestClient, anon_client: TestClient) -> None:
    sign_in = start(anon_client)
    response = client.post(f"/api/oauth/requests/{sign_in.request_id}", json={"approve": False})
    redirect = urlsplit(response.json()["redirect_uri"])
    assert parse_qs(redirect.query) == {"error": ["access_denied"], "state": ["client-state"]}
    assert client.get(f"/api/oauth/requests/{sign_in.request_id}").status_code == 404


def test_requests_are_answered_once(client: TestClient, anon_client: TestClient) -> None:
    sign_in = start(anon_client)
    approve(client, sign_in)
    response = client.post(f"/api/oauth/requests/{sign_in.request_id}", json={"approve": True})
    assert response.status_code == 404
    assert "expired or was already answered" in response.json()["detail"]


def test_requests_expire(client: TestClient, anon_client: TestClient) -> None:
    sign_in = start(anon_client)
    request = oauth._requests[sign_in.request_id]
    oauth._requests[sign_in.request_id] = dataclasses.replace(
        request, expires_at=utc_now() - timedelta(seconds=1)
    )
    assert client.get(f"/api/oauth/requests/{sign_in.request_id}").status_code == 404
    response = client.post(f"/api/oauth/requests/{sign_in.request_id}", json={"approve": True})
    assert response.status_code == 404


def test_unknown_request(client: TestClient) -> None:
    assert client.get("/api/oauth/requests/nope").status_code == 404


def test_code_works_once(client: TestClient, anon_client: TestClient) -> None:
    sign_in = start(anon_client)
    code = approve(client, sign_in)
    assert exchange(anon_client, sign_in, code).status_code == 200
    response = exchange(anon_client, sign_in, code)
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_grant"


def test_code_needs_the_pkce_verifier(client: TestClient, anon_client: TestClient) -> None:
    sign_in = start(anon_client)
    code = approve(client, sign_in)
    sign_in.verifier = secrets.token_urlsafe(48)
    assert exchange(anon_client, sign_in, code).status_code == 400


def test_code_is_for_its_client_only(client: TestClient, anon_client: TestClient) -> None:
    sign_in = start(anon_client)
    code = approve(client, sign_in)
    other = dataclasses.replace(sign_in, client=register(anon_client))
    assert exchange(anon_client, other, code).status_code == 400


def test_client_secret_is_checked(client: TestClient, anon_client: TestClient) -> None:
    sign_in = start(anon_client, register(anon_client, "client_secret_post"))
    code = approve(client, sign_in)
    sign_in.client["client_secret"] = "wrong"
    assert exchange(anon_client, sign_in, code).status_code == 401


def test_refresh_rotates_the_pair(
    client: TestClient, anon_client: TestClient, session: Session
) -> None:
    sign_in, tokens = connect(client, anon_client)
    assert access_works(session, tokens["access_token"])

    response = refresh(anon_client, sign_in, tokens["refresh_token"])
    assert response.status_code == 200, response.text
    new = response.json()
    assert access_works(session, new["access_token"])
    assert not access_works(session, tokens["access_token"])
    assert refresh(anon_client, sign_in, tokens["refresh_token"]).status_code == 400
    assert refresh(anon_client, sign_in, new["refresh_token"]).status_code == 200


def test_access_token_expires(
    client: TestClient, anon_client: TestClient, session: Session
) -> None:
    sign_in, tokens = connect(client, anon_client)
    for row in session.scalars(select(OAuthToken).where(OAuthToken.kind == "access")):
        row.expires_at = utc_now() - timedelta(seconds=1)
    session.flush()
    assert not access_works(session, tokens["access_token"])
    assert refresh(anon_client, sign_in, tokens["refresh_token"]).status_code == 200


def test_revoke_ends_both_tokens(
    client: TestClient, anon_client: TestClient, session: Session
) -> None:
    sign_in, tokens = connect(
        client, anon_client, client_info=register(anon_client, "client_secret_post")
    )
    response = anon_client.post("/revoke", data=sign_in.token_form(token=tokens["access_token"]))
    assert response.status_code == 200, response.text
    assert not access_works(session, tokens["access_token"])
    assert refresh(anon_client, sign_in, tokens["refresh_token"]).status_code == 400


def test_new_password_ends_mcp_access(
    client: TestClient, anon_client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign_in, tokens = connect(client, anon_client)
    monkeypatch.setattr(settings, "auth_password_hash", SecretStr(hash_password("new", n=2**10)))
    assert not access_works(session, tokens["access_token"])
    assert refresh(anon_client, sign_in, tokens["refresh_token"]).status_code == 400


def test_tokens_are_stored_only_as_hashes(
    client: TestClient, anon_client: TestClient, session: Session
) -> None:
    _, tokens = connect(client, anon_client)
    stored = session.scalars(select(OAuthToken.token_hash)).all()
    assert len(stored) == 2
    assert tokens["access_token"] not in stored
    assert tokens["refresh_token"] not in stored


def test_csrf_check_leaves_oauth_alone(anon_client: TestClient) -> None:
    response = anon_client.post(
        "/register",
        json={"redirect_uris": [REDIRECT_URI], "token_endpoint_auth_method": "none"},
        headers={"Origin": "https://claude.ai"},
    )
    assert response.status_code == 201


# Tools


def call(name: str, **arguments: object) -> object:
    _, structured = asyncio.run(mcp.call_tool(name, arguments))
    return structured.get("result", structured)


def test_update_changes_only_the_fields_given() -> None:
    client_id = call("create_client", client={"name": "Northwind"})["id"]
    project = call(
        "create_project",
        project={
            "client_id": client_id,
            "name": "Ordering site",
            "description": "Menu and checkout",
            "price": 48000,
            "started_on": "2026-09-01",
            "due_on": "2026-11-01",
        },
    )
    updated = call("update_project", project_id=project["id"], changes={"price": 50000})
    assert updated["price"] == 50000
    assert updated["description"] == "Menu and checkout"
    assert updated["due_on"] == "2026-11-01"

    cleared = call("update_project", project_id=project["id"], changes={"due_on": None})
    assert cleared["due_on"] is None
    assert cleared["price"] == 50000


def test_updates_are_validated_as_a_whole() -> None:
    client_id = call("create_client", client={"name": "Northwind"})["id"]
    project = call(
        "create_project",
        project={"client_id": client_id, "name": "Site", "price": 1000, "started_on": "2026-09-01"},
    )
    with pytest.raises(ToolError, match="can't be before the start date"):
        call("update_project", project_id=project["id"], changes={"due_on": "2026-01-01"})


def test_route_errors_become_tool_errors() -> None:
    with pytest.raises(ToolError, match="Client not found"):
        call("get_client", client_id=999999)
    with pytest.raises(ToolError, match="Client not found"):
        call("update_client", client_id=999999, changes={"name": "Nope"})


def test_contact_and_payment_tools() -> None:
    client_id = call("create_client", client={"name": "Northwind"})["id"]
    contact = call(
        "add_contact",
        client_id=client_id,
        contact={"kind": "line", "value": "@northwind"},
    )
    renamed = call(
        "update_contact", client_id=client_id, contact_id=contact["id"], changes={"value": "@nw"}
    )
    assert renamed["kind"] == "line"
    assert renamed["value"] == "@nw"

    project = call(
        "create_project",
        project={"client_id": client_id, "name": "Site", "price": 1000, "started_on": "2026-09-01"},
    )
    payment = call(
        "record_project_payment",
        project_id=project["id"],
        payment={"amount": 500, "paid_on": "2026-09-02", "note": "Deposit"},
    )
    assert payment["kind"] == "deposit"
    moved = call(
        "update_project_payment",
        project_id=project["id"],
        payment_id=payment["id"],
        changes={"amount": 400},
    )
    assert moved["amount"] == 400
    assert moved["note"] == "Deposit"
    assert call("get_project", project_id=project["id"])["total_paid"] == 400


def test_update_client_sets_the_discord_id() -> None:
    client_id = call("create_client", client={"name": "Northwind"})["id"]
    linked = call(
        "update_client", client_id=client_id, changes={"discord_user_id": "1207716883264966748"}
    )
    assert [(c["kind"], c["discord_user_id"]) for c in linked["contacts"]] == [
        ("discord", "1207716883264966748")
    ]

    renamed = call("update_client", client_id=client_id, changes={"name": "Northwind Coffee"})
    assert renamed["contacts"][0]["discord_user_id"] == "1207716883264966748"

    unlinked = call("update_client", client_id=client_id, changes={"discord_user_id": None})
    assert unlinked["contacts"][0]["discord_user_id"] is None
    assert unlinked["name"] == "Northwind Coffee"


def test_discord_ids_match_the_output_schemas() -> None:
    client = call(
        "create_client", client={"name": "Northwind", "discord_user_id": "1207716883264966748"}
    )
    contact = client["contacts"][0]
    call(
        "create_retainer",
        retainer={
            "client_id": client["id"],
            "amount": 3000,
            "due_day": 5,
            "collection": "ask",
            "ask_via_id": contact["id"],
            "started_on": "2026-09-01",
        },
    )
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    for name in ("list_clients", "list_retainers"):
        _, structured = asyncio.run(mcp.call_tool(name, {}))
        jsonschema.validate(structured, tools[name].outputSchema)
    assert contact["discord_user_id"] == "1207716883264966748"


def test_settings_tools() -> None:
    tokyo = {"timezone": "Asia/Tokyo", "user_name": None}
    assert call("update_settings", timezone="Asia/Tokyo") == tokyo
    assert call("get_settings") == tokyo
    named = tokyo | {"user_name": "Seria"}
    assert call("update_settings", user_name="Seria") == named
    # Only what's given changes, and nothing secret is sent.
    assert call("update_settings", timezone="Asia/Taipei") == named | {"timezone": "Asia/Taipei"}
    assert call("update_settings", user_name="") == named | {
        "timezone": "Asia/Taipei",
        "user_name": None,
    }
    with pytest.raises(ToolError, match="Unknown timezone"):
        call("update_settings", timezone="Mars/Olympus")
