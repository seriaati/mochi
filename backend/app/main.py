import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import discord, reminders
from app.auth import require_session
from app.config import settings as config
from app.csrf import CSRFMiddleware
from app.db import SessionDep, SessionLocal
from app.mcp_server import mcp
from app.routers import (
    auth,
    clients,
    keni,
    maintenance,
    oauth,
    overview,
    projects,
    retainers,
    settings,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    with SessionLocal() as session:
        discord.load(session)  # the Discord setup saved in Settings
    # Sends maintenance reminders, refreshes Discord profiles and syncs to Keni in the
    # background. Tests never enter the lifespan.
    task = asyncio.create_task(reminders.run_forever())
    async with mcp.session_manager.run():
        yield
    task.cancel()


app = FastAPI(title="Freelance Dashboard", lifespan=lifespan)

# Added first so it runs inside CORS, whose headers then reach the browser on a 403 too.
app.add_middleware(CSRFMiddleware)
if config.frontend_origins:
    # The frontend calls the API from another origin (e.g. dash.example.com -> api.example.com).
    # In development it goes through the Vite proxy instead and needs none of this.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.frontend_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )

# Public: health, and login, logout and the session check.
app.include_router(auth.router)

# Everything else needs a session. Include new routers here.
protected = APIRouter(dependencies=[Depends(require_session)])
protected.include_router(clients.router)
protected.include_router(projects.router)
protected.include_router(retainers.router)
protected.include_router(maintenance.router)
protected.include_router(settings.router)
protected.include_router(keni.router)
protected.include_router(overview.router)
protected.include_router(oauth.router)
app.include_router(protected)


@app.get("/api/health")
def health(session: SessionDep, response: Response) -> dict[str, str]:
    # Checks the database too, so the container healthcheck fails when the API can't serve data.
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "database": "unreachable"}
    return {"status": "ok"}


# MCP clients (see app/mcp_server.py): /mcp, and the OAuth endpoints and metadata they sign in
# with, which the spec puts at the root (/.well-known/..., /authorize, /token, /register,
# /revoke). Mounted last, so it only gets what no route above matches.
app.mount("/", mcp.streamable_http_app())
