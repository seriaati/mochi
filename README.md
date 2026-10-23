# freelance-dashboard

A small personal dashboard for freelance work: projects and their paid additions, clients and their contact methods, and monthly maintenance fees with Discord reminders.

- `backend/` — FastAPI, SQLAlchemy, Alembic, PostgreSQL (Python, managed with uv)
- `frontend/` — React, Vite, TypeScript (managed with bun)

## Development

Requires Docker, [uv](https://docs.astral.sh/uv/) and [bun](https://bun.sh/).

```sh
docker compose up -d                 # PostgreSQL on localhost:5433

cd backend
cp .env.example .env                 # then set AUTH_PASSWORD_HASH, and COOKIE_SECURE=false
uv run python -m app.passwords hash-password
uv run alembic upgrade head
uv run uvicorn app.main:app --reload # API on localhost:8000

cd frontend
bun install
bun run dev                          # app on localhost:5173, proxies /api to the backend
```

Tests: `cd backend && uv run pytest`. Lint and type-check the frontend with `bun run lint` and `bun run build`.

## Login

The dashboard has one user and a password. `backend/.env` holds only its scrypt hash, `AUTH_PASSWORD_HASH`, printed by `uv run python -m app.passwords hash-password`; without one, nobody can log in. Logging in sets an HttpOnly, SameSite=Lax session cookie that lasts 30 days from the last visit. Setting a new hash logs out every session.

## Deployment

With the frontend on Cloudflare Pages at `dash.example.com` and the API at `api.example.com`:

- Frontend build: `VITE_API_URL=https://api.example.com` (see `frontend/.env.example`).
- API: `AUTH_PASSWORD_HASH`, `FRONTEND_ORIGIN=https://dash.example.com` and `COOKIE_DOMAIN=.example.com` (see `backend/.env.example`). Keep `COOKIE_SECURE` on.
- API image: `docker build -t freelance-backend backend`, then `docker run -d -p 8000:8000 --env-file backend/.env freelance-backend`. It runs `alembic upgrade head` on start, exiting if that fails, and its healthcheck calls `/api/health`, which returns 503 when the database is unreachable. Run a single container: the reminder loop and login throttle live in one process.
- Login attempts are throttled per client IP. Behind a reverse proxy, run uvicorn with `--proxy-headers --forwarded-allow-ips=<proxy IP>` so it sees real client IPs, not the proxy's.
