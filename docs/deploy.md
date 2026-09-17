# Deploy (Compose / Railway-style)

Service ChatBot is two apps plus Postgres and Redis. Background loops (debounce, workflow timers, auto-steps) already run inside the FastAPI lifespan — **do not** start a second worker process.

This file is documentation only. It does not log in to Railway or deploy to a live cloud.

## Services

| Service | Image / Dockerfile | Port | Notes |
|---|---|---|---|
| Postgres 16 | `postgres:16` | internal | `DATABASE_URL` |
| Redis 7 | `redis:7` | internal | `REDIS_URL` — rate limits + debounce |
| API | `docker/Dockerfile.backend` | 8000 | `uvicorn app.main:app` (no `--reload`) |
| Frontend | `docker/Dockerfile.frontend` | 3000 | Next.js standalone; off-localhost the client uses relative URLs |

Run locally in production mode:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Admin: http://localhost:3000/admin/login · API health: http://localhost:8000/health

## Required environment (production)

Set `ENVIRONMENT=production`. Startup **fails fast** if `SECRET_ENCRYPTION_KEY` is missing or not a valid Fernet key.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres |
| `REDIS_URL` | Redis |
| `SECRET_ENCRYPTION_KEY` | Fernet key for channel/notification tokens (required in production) |
| `JWT_SECRET_KEY` | Admin JWT signing |
| `APP_URL` | Public **HTTPS** origin of the API (webhooks) |
| `CORS_ORIGINS` | Frontend origin(s) |
| `OPENAI_API_KEY` | LLM / RAG |
| `ENVIRONMENT` | `production` |

Optional channel credentials: `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET`, `TIKTOK_APP_ID`, `TIKTOK_APP_SECRET`, `TIKTOK_MESSAGING_ENABLED`.

Messenger webhook paths (`/api/v1/telegram/webhook`, `/viber/webhook`, `/instagram/webhook`, `/tiktok/webhook`) and `/health` are **not** IP-rate-limited. Other API/admin routes default to 60 requests/minute per IP (Redis when available).

## HTTPS for Viber / Instagram / TikTok

Those platforms reject self-signed and often `http://` webhooks. Put a trusted reverse proxy (or a host-provided HTTPS domain) in front of the API and set `APP_URL` to that HTTPS origin, e.g. `https://api.example.com`. Telegram can work on HTTP in some setups, but use HTTPS in production.

## Railway-style

Provision four pieces: Postgres, Redis, API, frontend.

- API: Dockerfile `docker/Dockerfile.backend`, health check `/health`.
- Frontend: Dockerfile `docker/Dockerfile.frontend`. Pass `NEXT_PUBLIC_API_URL` at **build** time only if the browser cannot use same-origin relative URLs.
- Wire `DATABASE_URL` and `REDIS_URL` from the plugins.
- Run `python scripts/init_db.py` once (or on each deploy) before serving traffic. Compose prod uses a one-shot `migrate` service.

Do not run a second FastAPI process for background jobs.

## Smoke test

After the stack is up, follow [docs/smoke-test.md](smoke-test.md).
