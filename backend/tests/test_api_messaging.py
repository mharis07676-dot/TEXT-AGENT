from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.messaging.enums import MessagingChannel, MessagingProviderName
from app.messaging.schemas import NormalizedInboundMessage


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("DATABASE_URL_SYNC", "sqlite:///:memory:")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    from app.config import get_settings

    get_settings.cache_clear()

    with patch("app.main.init_db", new=AsyncMock()), patch(
        "app.main.validate_required_settings", new=MagicMock()
    ):
        app = create_app()
        with TestClient(app) as test_client:
            yield test_client

    get_settings.cache_clear()


def test_messaging_health(client):
    response = client.get("/api/v1/messaging/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "twilio_configured" in payload
    assert "openai_configured" in payload
    assert "token" not in payload
    assert "secret" not in str(payload).lower()


def test_root_and_health(client):
    assert client.get("/").status_code == 200
    assert client.get("/health").status_code == 200


def test_inbound_rejects_invalid_signature(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACxxx")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "secret-token")
    monkeypatch.setenv("TWILIO_WEBHOOK_BASE_URL", "https://example.com")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("TWILIO_SMS_FROM_NUMBER", "+15557654321")

    from app.config import get_settings

    get_settings.cache_clear()

    with patch("app.main.init_db", new=AsyncMock()), patch(
        "app.main.validate_required_settings", new=MagicMock()
    ):
        app = create_app()
        with TestClient(app) as test_client:
            response = test_client.post(
                "/api/v1/messaging/twilio/inbound",
                data={
                    "MessageSid": "SM9",
                    "From": "+15551234567",
                    "To": "+15557654321",
                    "Body": "hi",
                },
                headers={"X-Twilio-Signature": "bad"},
            )
    assert response.status_code == 403
    get_settings.cache_clear()
