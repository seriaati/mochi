"""Refuses cross-site writes.

The session cookie is SameSite=Lax, so other sites can't send it with a POST from script, but
sibling subdomains count as the same site. As a second check, a POST, PUT, PATCH or DELETE is
refused with 403 when its Origin header (or, without one, its Referer) is neither the API's own
origin nor one of FRONTEND_ORIGIN. Requests with neither header, such as curl's, pass: browsers
send Origin on every cross-origin write.
"""

from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _origin_of(url: str) -> str | None:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else None


def _source(request: Request) -> str | None:
    """Where the request came from, or None when the client didn't say. A Referer that isn't an
    absolute URL gives "", which matches nothing."""
    if (origin := request.headers.get("origin")) is not None:
        return origin
    if (referer := request.headers.get("referer")) is not None:
        return _origin_of(referer) or ""
    return None


class CSRFMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] in UNSAFE_METHODS:
            request = Request(scope)
            source = _source(request)
            own = f"{request.url.scheme}://{request.url.netloc}"
            allowed = {own, *settings.frontend_origins}
            if source is not None and source.lower() not in {o.lower() for o in allowed}:
                response = JSONResponse({"detail": "Cross-site request refused."}, status_code=403)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
