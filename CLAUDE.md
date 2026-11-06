# Mochi

Mochi is a single-user dashboard for freelance work: a FastAPI + PostgreSQL backend in `backend/`, and a React + Vite frontend in `frontend/` (bun). See `README.md` for setup.

## UI work

Before building or changing anything in the frontend (pages, features, components, styles), read `frontend/DESIGN.md` and follow it. The "Bento" look is a deliberate choice; new UI must match it, not reinterpret it.

## Android app

`frontend/android/` is a Capacitor shell (`moe.seria.mochi`) that loads the user's Mochi web app as its runtime `server.url`, asked for at the first start by `ServerActivity`. Native bits are in `MochiPlugin.kt` (JS name `Mochi`). `frontend/src/native.ts` holds everything app-only (`inApp`, the plugin, Back button, notification taps, the GitHub update check); `frontend/src/push.ts` hands the server's Firebase settings to the app and registers its FCM token with the API (`backend/app/push.py`, `backend/app/routers/notifications.py`). `scripts/build-android.sh` builds the signed APK in Docker (`frontend/android/mochi.apk`; `VERSION_NAME` / `VERSION_CODE`, default dev / 1); `.github/workflows/android.yml` releases it on `v*` tags. In-app UI, such as its Settings tiles, still follows `frontend/DESIGN.md`.
