# Synas Labs Text Agent

Production-oriented **SMS + WhatsApp** AI text agent infrastructure with an ops dashboard.

One shared brain and conversation system for both channels. Twilio is the transport; OpenAI powers replies; PostgreSQL is the source of truth for history.

> Voice calling lives in the separate [AI-CALLING-AGENT](https://github.com/mharis07676-dot/AI-CALLING-AGENT) repo. This service focuses on text messaging and reuses the same FastAPI / SQLAlchemy / tenant / dashboard patterns.

## Architecture

```text
Customer
  ├─ SMS
  └─ WhatsApp
        │
      Twilio
        │
        v
FastAPI Messaging Webhook
        │
        v
Channel Normalizer
        │
        v
Conversation Service
   ├─ PostgreSQL
   └─ AI Text Agent (OpenAI)
        │
        v
Response Service → Twilio → SMS / WhatsApp
        │
        v
Next.js Dashboard (Inbox / Contacts / Analytics)
```

## Stack

| Part | Technology |
|---|---|
| Backend | FastAPI |
| Frontend | Next.js + TypeScript + Tailwind |
| Database | PostgreSQL + SQLAlchemy async |
| Messaging | Twilio SMS + WhatsApp |
| AI | OpenAI Chat Completions |
| Deploy | Railway / Docker (API + UI in one service) |

## Quick start

```bash
cp .env.example .env

# Postgres
docker compose up db -d

cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
cd dashboard
cp .env.local.example .env.local
npm install
npm run dev
```

- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health
- Messaging health: http://localhost:8000/api/v1/messaging/health
- Dashboard: http://localhost:3000

Default bootstrap admin (created on API startup if missing):

- tenant: `synas`
- email: `admin@synas.local`
- password: `changeme123`

Change these via `BOOTSTRAP_ADMIN_*` env vars before production use.

## Twilio webhooks

Configure both SMS and WhatsApp webhooks to:

- Inbound: `https://<YOUR-RAILWAY-HOST>/api/v1/messaging/twilio/inbound`
- Status: `https://<YOUR-RAILWAY-HOST>/api/v1/messaging/twilio/status`

Set `TWILIO_WEBHOOK_BASE_URL` to that same public HTTPS origin so signature validation works behind Railway's reverse proxy.

## Dashboard APIs

Authenticated dashboard clients use Bearer JWT from `/api/v1/auth/login`.

| Action | Endpoint |
|---|---|
| Login | `POST /api/v1/auth/login` |
| Current user | `GET /api/v1/auth/me` |
| List conversations | `GET /api/v1/messaging/conversations` |
| Get conversation | `GET /api/v1/messaging/conversations/{id}` |
| Update conversation | `PATCH /api/v1/messaging/conversations/{id}` |
| Toggle AI mode | `POST /api/v1/messaging/conversations/{id}/ai-mode` |
| List messages | `GET /api/v1/messaging/conversations/{id}/messages` |
| Send human message | `POST /api/v1/messaging/conversations/{id}/messages` |
| List contacts | `GET /api/v1/messaging/contacts` |
| Get contact | `GET /api/v1/messaging/contacts/{id}` |
| Stats | `GET /api/v1/messaging/stats` |
| Analytics | `GET /api/v1/messaging/analytics` |
| Health (safe) | `GET /api/v1/messaging/health` |

## Migrations

Dev/startup creates tables via SQLAlchemy metadata.

Explicit SQL:

```bash
psql "$DATABASE_URL_SYNC" -f backend/migrations/001_text_messaging.sql
```

Alembic:

```bash
cd backend
alembic upgrade head
```

## Tests

```bash
cd backend
pytest -q

cd ../dashboard
npm test
npm run typecheck
npm run build
```

## AI / Human mode

`conversations.ai_enabled`:

- `true` → AI may auto-reply
- `false` → inbound messages are stored; no automatic AI reply

Toggle:

```bash
curl -X POST http://localhost:8000/api/v1/messaging/conversations/<id>/ai-mode \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d "{\"ai_enabled\": false}"
```
