import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app import auth
from app.auth import CookieToken, NowDep
from app.config import settings
from app.db import SessionDep
from app.passwords import verify_password
from app.schemas.auth import LoginIn, SessionOut
from app.throttle import Limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Login attempts allowed per client IP, and from everyone together, in any minute. Behind a
# reverse proxy, uvicorn needs --proxy-headers and --forwarded-allow-ips to see real client IPs.
login_limiter = Limiter(per_key=5, total=30, window=60)
# Seconds a wrong password waits before its answer.
FAILED_LOGIN_DELAY = 1.0


@router.get("/session")
def session_status(is_authenticated: Annotated[bool, Depends(auth.authenticated)]) -> SessionOut:
    return SessionOut(authenticated=is_authenticated)


@router.post("/login")
def login(
    body: LoginIn, request: Request, response: Response, session: SessionDep, now: NowDep
) -> SessionOut:
    if settings.auth_password_hash is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Login is disabled: no password is set. Set AUTH_PASSWORD_HASH on the server "
            "(make one with `uv run python -m app.passwords hash-password`) and restart it.",
        )
    wait = login_limiter.hit(request.client.host if request.client else "unknown")
    if wait is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many login attempts. Try again in {wait} s.",
            headers={"Retry-After": str(wait)},
        )
    if not verify_password(body.password, settings.auth_password_hash.get_secret_value()):
        time.sleep(FAILED_LOGIN_DELAY)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong password.")
    auth.set_cookie(response, auth.create_session(session, now))
    return SessionOut(authenticated=True)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, session: SessionDep, token: CookieToken = None) -> None:
    if token is not None:
        auth.end_session(session, token)
    auth.clear_cookie(response)
