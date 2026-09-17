# Service ChatBot

Web app for service businesses (salon, clinic, school, shop, support) to create an AI chatbot and connect it to Telegram, Viber, Instagram, and TikTok.

**Current product:** admin login, 8-step agent wizard, RAG, in-browser web chat, inbox + human handoff, CRM board, questionnaires, stats, audit, and four channels (Telegram, Viber, Instagram, TikTok). Block E adds a visible support matrix, webhook idempotency, Redis-backed rate limits (webhooks exempt), production encryption-key guard, and deploy artifacts.

See [docs/development-plan.md](docs/development-plan.md), [docs/smoke-test.md](docs/smoke-test.md), and [docs/deploy.md](docs/deploy.md).

## Run locally (Docker)

Requires Docker with Compose v2.

```bash
./scripts/dev-setup.sh   # env files, Postgres/Redis, migrations + bootstrap admin
./scripts/dev-up.sh      # backend + frontend
```

| URL | Purpose |
|---|---|
| http://localhost:3000/admin/login | Admin login |
| http://localhost:3000/admin/agents | Agent list |
| http://localhost:3000/admin/agents/create | 8-step wizard |
| http://localhost:3000/admin/agents/{id}/channels | Four connectors + support matrix |
| http://localhost:3000/admin/conversations | Inbox / handoff |
| http://localhost:3000/chat/{agentId} | Web chat test |
| http://localhost:8000/health | API health |

### Bootstrap admin

Created automatically on first migrate if no admin exists:

- Email: `admin@example.com`
- Password: `changeme123`

Override via `ADMIN_BOOTSTRAP_EMAIL` / `ADMIN_BOOTSTRAP_PASSWORD` in `backend/.env`.

Login: `POST /api/v1/admin/auth/login-password` → JWT. `ADMIN_TOKEN` is a dev fallback only.

### Create an agent

1. Log in at `/admin/login`
2. Open **Agents** → **Create agent**
3. Complete the 8-step wizard and activate
4. Upload FAQ files under **Knowledge (RAG)** for the agent
5. Test at `/chat/{agentId}`

Set `OPENAI_API_KEY` in `backend/.env` for live LLM/RAG replies.

Production-style Compose (no live cloud deploy): `docker compose -f docker-compose.prod.yml up -d --build`. `ENVIRONMENT=production` requires a valid `SECRET_ENCRYPTION_KEY`. Messenger webhook paths are not IP-rate-limited.

Stop:

```bash
./scripts/dev-down.sh
# ./scripts/dev-down.sh --volumes   # also resets Postgres/Redis data
```

## Stack

- Backend: FastAPI (Python 3.11) on port 8000
- Frontend: Next.js (App Router) on port 3000
- Postgres 16 + Redis 7 in Compose (not published on host 5432/6379)

Env files (`/.env`, `backend/.env`, `frontend/.env.local`) are gitignored.
