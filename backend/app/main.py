import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import reminders
from app.routers import clients, maintenance, overview, projects, retainers, settings


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Sends maintenance reminders and refreshes Discord profiles in the background. Tests never
    # enter the lifespan.
    task = asyncio.create_task(reminders.run_forever())
    yield
    task.cancel()


app = FastAPI(title="Freelance Dashboard", lifespan=lifespan)
app.include_router(clients.router)
app.include_router(projects.router)
app.include_router(retainers.router)
app.include_router(maintenance.router)
app.include_router(settings.router)
app.include_router(overview.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
