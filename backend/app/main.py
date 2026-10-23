import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import reminders
from app.auth import require_session
from app.config import settings as config
from app.csrf import CSRFMiddleware
from app.routers import auth, clients, maintenance, overview, projects, retainers, settings


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Sends maintenance reminders and refreshes Discord profiles in the background. Tests never
    # enter the lifespan.
    task = asyncio.create_task(reminders.run_forever())
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
protected.include_router(overview.router)
app.include_router(protected)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
