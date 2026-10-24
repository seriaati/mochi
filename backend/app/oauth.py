"""OAuth for MCP clients, such as Claude connecting to /mcp (see app/mcp_server.py).

The MCP SDK serves the OAuth endpoints (/register, /authorize, /token, /revoke and the
.well-known metadata) and calls the Provider below to keep clients, codes and tokens. /authorize
sends the user to the frontend's /oauth/authorize page, which shows which client is asking and,
once the user approves while logged in, gets the client a code through /api/oauth/requests (see
app/routers/oauth.py). The client trades the code for an access token and a refresh token.

Codes and tokens are stored as their SHA-256 and stop working when AUTH_PASSWORD_HASH changes,
like login sessions. Requests waiting for the user's answer live in memory, so a restart drops
them and the client has to connect again.
"""

import asyncio
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlencode

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull
from mcp.shared.auth import OAuthToken as TokenResponse
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.auth import password_fingerprint, token_hash
from app.clock import utc_now
from app.config import settings
from app.db import SessionLocal
from app.models import OAuthClient, OAuthCode, OAuthToken

# The only scope: everything the dashboard can do.
SCOPE = "dashboard"
REQUEST_LIFETIME = timedelta(minutes=10)
CODE_LIFETIME = timedelta(minutes=5)
ACCESS_LIFETIME = timedelta(hours=1)
# Each refresh issues a new refresh token, so a client that stays in use stays connected.
REFRESH_LIFETIME = timedelta(days=30)

ACCESS = "access"
REFRESH = "refresh"


@dataclass(frozen=True)
class Request:
    """A client's request for access, waiting for the user's answer."""

    client: OAuthClientInformationFull
    params: AuthorizationParams
    expires_at: datetime


_requests: dict[str, Request] = {}


def add_request(
    client: OAuthClientInformationFull, params: AuthorizationParams, now: datetime
) -> str:
    """Holds a request for the user to answer and returns its ID. Drops expired ones."""
    for request_id, request in list(_requests.items()):
        if request.expires_at <= now:
            _requests.pop(request_id, None)
    request_id = secrets.token_urlsafe(16)
    _requests[request_id] = Request(client, params, now + REQUEST_LIFETIME)
    return request_id


def pending(request_id: str, now: datetime) -> Request | None:
    request = _requests.get(request_id)
    return request if request is not None and request.expires_at > now else None


def answer(session: Session, now: datetime, request_id: str, approve: bool) -> str | None:
    """Answers a request and returns where to send the user: back to the client with a code, or
    with access_denied. None when no such request is waiting."""
    request = _requests.pop(request_id, None)
    if request is None or request.expires_at <= now:
        return None
    params = request.params
    if not approve:
        return construct_redirect_uri(
            str(params.redirect_uri), error="access_denied", state=params.state
        )
    fingerprint = password_fingerprint()
    assert fingerprint is not None, "approve only with a password hash configured"
    code = secrets.token_urlsafe(32)
    session.add(
        OAuthCode(
            code_hash=token_hash(code),
            client_id=request.client.client_id,
            params=params.model_dump(
                mode="json",
                include={
                    "code_challenge",
                    "redirect_uri",
                    "redirect_uri_provided_explicitly",
                    "resource",
                },
            ),
            password_fingerprint=fingerprint,
            expires_at=now + CODE_LIFETIME,
        )
    )
    session.commit()
    return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)


def get_client(
    session: Session, now: datetime, client_id: str
) -> OAuthClientInformationFull | None:
    row = session.get(OAuthClient, client_id)
    return OAuthClientInformationFull.model_validate(row.info) if row else None


def register_client(session: Session, now: datetime, info: OAuthClientInformationFull) -> None:
    assert info.client_id is not None, "the SDK assigns client IDs"
    session.add(
        OAuthClient(
            client_id=info.client_id,
            info=info.model_dump(mode="json", exclude_none=True),
            created_at=now,
        )
    )
    session.commit()


def _live(fingerprint: str) -> bool:
    """Whether a code or token was issued under the current password."""
    return fingerprint == password_fingerprint()


def load_code(
    session: Session, now: datetime, client_id: str | None, code: str
) -> AuthorizationCode | None:
    row = session.get(OAuthCode, token_hash(code))
    if row is None or row.client_id != client_id or not _live(row.password_fingerprint):
        return None
    return AuthorizationCode(
        code=code,
        client_id=row.client_id,
        scopes=[SCOPE],
        expires_at=row.expires_at.timestamp(),
        **row.params,
    )


def _issue(
    session: Session, now: datetime, client_id: str, scopes: list[str], resource: str | None
) -> TokenResponse:
    """A new access and refresh token pair. Clears out expired codes and tokens."""
    session.execute(delete(OAuthCode).where(OAuthCode.expires_at <= now))
    session.execute(delete(OAuthToken).where(OAuthToken.expires_at <= now))
    fingerprint = password_fingerprint()
    assert fingerprint is not None, "codes and tokens load only with a password hash configured"
    grant_id = uuid.uuid4().hex
    access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    for kind, token, lifetime in [
        (ACCESS, access, ACCESS_LIFETIME),
        (REFRESH, refresh, REFRESH_LIFETIME),
    ]:
        session.add(
            OAuthToken(
                token_hash=token_hash(token),
                kind=kind,
                grant_id=grant_id,
                client_id=client_id,
                scopes=scopes,
                resource=resource,
                password_fingerprint=fingerprint,
                expires_at=now + lifetime,
            )
        )
    session.commit()
    return TokenResponse(
        access_token=access,
        expires_in=int(ACCESS_LIFETIME.total_seconds()),
        scope=" ".join(scopes),
        refresh_token=refresh,
    )


def exchange_code(session: Session, now: datetime, code: AuthorizationCode) -> TokenResponse:
    # Deleting decides which of two simultaneous exchanges of one code wins.
    used = session.execute(delete(OAuthCode).where(OAuthCode.code_hash == token_hash(code.code)))
    if used.rowcount == 0:
        raise TokenError("invalid_grant", "authorization code already used")
    return _issue(session, now, code.client_id, code.scopes, code.resource)


def _load_token(session: Session, now: datetime, token: str, kind: str) -> OAuthToken | None:
    row = session.get(OAuthToken, token_hash(token))
    if row is None or row.kind != kind or row.expires_at <= now:
        return None
    return row if _live(row.password_fingerprint) else None


def load_refresh_token(
    session: Session, now: datetime, client_id: str | None, token: str
) -> RefreshToken | None:
    row = _load_token(session, now, token, REFRESH)
    if row is None or row.client_id != client_id:
        return None
    return RefreshToken(
        token=token,
        client_id=row.client_id,
        scopes=row.scopes,
        expires_at=int(row.expires_at.timestamp()),
        resource=row.resource,
    )


def exchange_refresh_token(
    session: Session, now: datetime, token: RefreshToken, scopes: list[str]
) -> TokenResponse:
    """Ends the token's grant, both tokens, and starts a new one."""
    row = session.get(OAuthToken, token_hash(token.token))
    if row is None:
        raise TokenError("invalid_grant", "refresh token already used")
    session.execute(delete(OAuthToken).where(OAuthToken.grant_id == row.grant_id))
    return _issue(session, now, token.client_id, scopes or token.scopes, token.resource)


def load_access_token(session: Session, now: datetime, token: str) -> AccessToken | None:
    row = _load_token(session, now, token, ACCESS)
    if row is None:
        return None
    return AccessToken(
        token=token,
        client_id=row.client_id,
        scopes=row.scopes,
        expires_at=int(row.expires_at.timestamp()),
        resource=row.resource,
    )


def revoke(session: Session, now: datetime, token: str) -> None:
    """Ends the token's grant: revoking either token of a pair revokes both."""
    row = session.get(OAuthToken, token_hash(token))
    if row is not None:
        session.execute(delete(OAuthToken).where(OAuthToken.grant_id == row.grant_id))
        session.commit()


async def _run[T](fn: Callable[..., T], *args: object) -> T:
    """Runs fn(session, now, *args) off the event loop, as FastAPI runs sync routes."""

    def call() -> T:
        with SessionLocal() as session:
            return fn(session, utc_now(), *args)

    return await asyncio.to_thread(call)


class Provider(OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]):
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return await _run(get_client, client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        await _run(register_client, client_info)

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        request_id = add_request(client, params, utc_now())
        return f"{settings.app_url}/oauth/authorize?{urlencode({'request': request_id})}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        return await _run(load_code, client.client_id, authorization_code)

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> TokenResponse:
        return await _run(exchange_code, authorization_code)

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        return await _run(load_refresh_token, client.client_id, refresh_token)

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> TokenResponse:
        return await _run(exchange_refresh_token, refresh_token, scopes)

    async def load_access_token(self, token: str) -> AccessToken | None:
        return await _run(load_access_token, token)

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        await _run(revoke, token.token)
