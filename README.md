# Synas Labs Text Agent

Production-oriented **SMS + WhatsApp** AI text agent infrastructure.

One shared brain and conversation system for both channels. Twilio is the transport; OpenAI powers replies; PostgreSQL is the source of truth for history.

> Voice calling lives in the separate [AI-CALLING-AGENT](https://github.com/mharis07676-dot/AI-CALLING-AGENT) repo. This service focuses on text messaging and reuses the same FastAPI / SQLAlchemy / tenant patterns.

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
```

## Stack

| Part | Technology |
|---|---|
| Backend | FastAPI |
| Database | PostgreSQL + SQLAlchemy async |
| Messaging | Twilio SMS + WhatsApp |
| AI | OpenAI Chat Completions |
| Deploy | Railway / Docker |

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

API docs: http://localhost:8000/docs  
Health: http://localhost:8000/health  
Messaging health: http://localhost:8000/api/v1/messaging/health

## Twilio webhooks

Configure both SMS and WhatsApp webhooks to:

- Inbound: `https://<YOUR-RAILWAY-HOST>/api/v1/messaging/twilio/inbound`
- Status: `https://<YOUR-RAILWAY-HOST>/api/v1/messaging/twilio/status`

Set `TWILIO_WEBHOOK_BASE_URL` to that same public HTTPS origin so signature validation works behind Railway's reverse proxy.

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
```

## AI / Human mode

`conversations.ai_enabled`:

- `true` → AI may auto-reply
- `false` → inbound messages are stored; no automatic AI reply

Toggle:

```bash
curl -X POST http://localhost:8000/api/v1/messaging/conversations/<id>/ai-mode \
  -F ai_enabled=false
```
