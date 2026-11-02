#!/usr/bin/env bash
# dev.sh — run frontend + backend dev servers together
#   ./dev.sh          against the database in backend/.env
#   ./dev.sh --demo   against its own mochi_demo database, filled with fresh demo data on each run
#                     (password: mochi). Starts the database; leaves your own data alone.
set -euo pipefail

case "${1:-}" in
  "") ;;
  --demo)
    docker compose up -d --wait db
    # psql inside the container, so this machine needs no PostgreSQL client.
    if [ -z "$(docker compose exec -T db psql -U freelance -d freelance -tAc "SELECT 1 FROM pg_database WHERE datname = 'mochi_demo'")" ]; then
      docker compose exec -T db psql -U freelance -d freelance -qc 'CREATE DATABASE mochi_demo'
    fi
    # These override backend/.env, which isn't needed at all.
    export DATABASE_URL=postgresql+psycopg://freelance:freelance@localhost:5433/mochi_demo
    export DEMO=true COOKIE_SECURE=false
    AUTH_PASSWORD_HASH=$(cd backend && uv run python -c "from app.passwords import hash_password; print(hash_password('mochi'))")
    export AUTH_PASSWORD_HASH
    (cd backend && uv run alembic upgrade head && uv run python -m app.demo reset)
    echo "Demo data ready: log in at http://localhost:5173 with the password mochi"
    ;;
  *)
    echo "usage: ./dev.sh [--demo]" >&2
    exit 1
    ;;
esac

pids=()

cleanup() {
  trap - INT TERM EXIT
  for pid in "${pids[@]}"; do
    # kill each child's process group to catch grandchildren (uvicorn, vite)
    kill -- -"$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# setsid: give each server its own process group so we can kill the whole tree
setsid bash -c 'cd backend  && exec uv run uvicorn app.main:app --reload --port 8000' &
pids+=($!)
setsid bash -c 'cd frontend && exec bun run dev' &
pids+=($!)

wait
