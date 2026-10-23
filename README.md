# freelance-dashboard

A small personal dashboard for freelance work: projects and their paid additions, clients and their contact methods, and monthly maintenance fees with Discord reminders.

- `backend/` — FastAPI, SQLAlchemy, Alembic, PostgreSQL (Python, managed with uv)
- `frontend/` — React, Vite, TypeScript (managed with bun)

## Development

Requires Docker, [uv](https://docs.astral.sh/uv/) and [bun](https://bun.sh/).

```sh
docker compose up -d                 # PostgreSQL on localhost:5433

cd backend
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload # API on localhost:8000

cd frontend
bun install
bun run dev                          # app on localhost:5173, proxies /api to the backend
```

Tests: `cd backend && uv run pytest`. Lint and type-check the frontend with `bun run lint` and `bun run build`.
