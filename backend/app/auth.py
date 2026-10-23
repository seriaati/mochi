"""Login sessions for the dashboard's single user.

Logging in with the password (see app/passwords.py) creates a row in auth_sessions and sets a
cookie holding a random token; the row stores only the token's SHA-256. A session lasts
SESSION_LIFETIME from its last use, and ends early on logout or when AUTH_PASSWORD_HASH changes.
Every /api route except health and /api/auth requires one (see app/main.py).
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.clock import get_now
from app.config import settings
from app.db import SessionDep
from app.models import AuthSession
from app.passwords import fingerprint

COOKIE_NAME = "freelance_session"
SESSION_LIFETIME = timedelta(days=30)
# How far behind a full lifetime an expiry may fall before a request slides it forward and
# re-sends the cookie. Keeps that to once a day instead of on every response.
REFRESH_AFTER = timedelta(days=1)

NowDep = Annotated[datetime, Depends(get_now)]
CookieToken = Annotated[str | None, Cookie(alias=COOKIE_NAME)]


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _password_fingerprint() -> str | None:
    encoded = settings.auth_password_hash
    return fingerprint(encoded.get_secret_value()) if encoded else None


def create_session(session: Session, now: datetime) -> str:
    """Starts a session and returns its token for the cookie. Clears out expired sessions."""
    session.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
    password = _password_fingerprint()
    assert password is not None, "log in only with a password hash configured"
    token = secrets.token_urlsafe(32)
    session.add(
        AuthSession(
            token_hash=token_hash(token),
            password_fingerprint=password,
            created_at=now,
            expires_at=now + SESSION_LIFETIME,
            last_seen=now,
        )
    )
    session.commit()
    return token


def end_session(session: Session, token: str) -> None:
    session.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(token)))
    session.commit()


def set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        path="/",
        domain=settings.cookie_domain,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def clear_cookie(response: Response) -> None:
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        domain=settings.cookie_domain,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def authenticated(
    session: SessionDep, now: NowDep, response: Response, token: CookieToken = None
) -> bool:
    """Whether the request carries a live session. Records the use and slides its expiry."""
    password = _password_fingerprint()
    if token is None or password is None:
        return False
    row = session.scalars(
        select(AuthSession).where(AuthSession.token_hash == token_hash(token))
    ).one_or_none()
    if row is None:
        return False
    if row.expires_at <= now or row.password_fingerprint != password:
        session.delete(row)
        session.commit()
        return False
    row.last_seen = now
    if now + SESSION_LIFETIME - row.expires_at >= REFRESH_AFTER:
        row.expires_at = now + SESSION_LIFETIME
        set_cookie(response, token)
    session.commit()
    return True


def require_session(is_authenticated: Annotated[bool, Depends(authenticated)]) -> None:
    if not is_authenticated:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in.")
