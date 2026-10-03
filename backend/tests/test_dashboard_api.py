from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.messaging.enums import MessagingChannel
from app.models import (
    Contact,
    Conversation,
    ConversationStatus,
    Message,
    MessageDirection,
    MessageRole,
    Tenant,
    User,
    UserRole,
)


@pytest.fixture
def api_client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("DATABASE_URL_SYNC", "sqlite:///:memory:")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    from app.config import get_settings

    get_settings.cache_clear()

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def prepare():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            tenant = Tenant(id=uuid4(), name="Synas", slug="synas", is_active=True, settings={})
            user = User(
                id=uuid4(),
                tenant_id=tenant.id,
                email="admin@synas.local",
                full_name="Admin",
                hashed_password=hash_password("changeme123"),
                role=UserRole.OWNER,
                is_active=True,
            )
            contact = Contact(
                id=uuid4(),
                tenant_id=tenant.id,
                phone_number="+923001234567",
                name="Haris",
            )
            conversation = Conversation(
                id=uuid4(),
                tenant_id=tenant.id,
                contact_id=contact.id,
                channel=MessagingChannel.WHATSAPP,
                status=ConversationStatus.ACTIVE,
                ai_enabled=True,
                metadata_json={"unread_count": 1},
            )
            message = Message(
                id=uuid4(),
                tenant_id=tenant.id,
                conversation_id=conversation.id,
                role=MessageRole.USER,
                direction=MessageDirection.INBOUND,
                channel=MessagingChannel.WHATSAPP,
                body="Hello pricing?",
                provider_status="received",
            )
            session.add_all([tenant, user, contact, conversation, message])
            await session.commit()
            return tenant, user, conversation

    tenant, user, conversation = asyncio.run(prepare())

    with patch("app.main.init_db", new=AsyncMock()), patch(
        "app.main.validate_required_settings", new=MagicMock()
    ):
        app = create_app()
        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)
        token = create_access_token(
            user_id=user.id,
            tenant_id=tenant.id,
            role=user.role,
            email=user.email,
        )
        yield client, token, str(conversation.id)
        app.dependency_overrides.clear()
        client.close()

    asyncio.run(engine.dispose())
    get_settings.cache_clear()


def test_login_and_list_conversations(api_client):
    client, token, _conversation_id = api_client
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@synas.local",
            "password": "changeme123",
            "tenant_slug": "synas",
        },
    )
    assert login.status_code == 200
    assert "access_token" in login.json()

    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/v1/messaging/conversations", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    assert payload["items"][0]["channel"] == "whatsapp"


def test_messages_and_ai_mode(api_client):
    client, token, conversation_id = api_client
    headers = {"Authorization": f"Bearer {token}"}

    messages = client.get(
        f"/api/v1/messaging/conversations/{conversation_id}/messages",
        headers=headers,
    )
    assert messages.status_code == 200
    body = messages.json()
    assert body["items"][0]["role"] == "user"
    assert body["items"][0]["body"] == "Hello pricing?"

    mode = client.post(
        f"/api/v1/messaging/conversations/{conversation_id}/ai-mode",
        headers=headers,
        json={"ai_enabled": False},
    )
    assert mode.status_code == 200
    assert mode.json()["ai_enabled"] is False


def test_send_human_message(api_client):
    client, token, conversation_id = api_client
    headers = {"Authorization": f"Bearer {token}"}
    message_id = uuid4()

    with patch(
        "app.api.messaging.OutboundMessageService.send_message",
        new=AsyncMock(
            return_value=SimpleNamespace(
                id=message_id,
                conversation_id=UUID(conversation_id),
                role=MessageRole.HUMAN,
                direction=MessageDirection.OUTBOUND,
                channel=MessagingChannel.WHATSAPP,
                body="I can help with that.",
                provider_status="queued",
                provider_message_sid="SMhuman1",
                created_at=None,
            )
        ),
    ):
        response = client.post(
            f"/api/v1/messaging/conversations/{conversation_id}/messages",
            headers=headers,
            json={"body": "I can help with that."},
        )
    assert response.status_code == 201
    assert response.json()["role"] == "human"
