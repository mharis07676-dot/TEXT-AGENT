from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.config import Settings
from app.messaging.enums import ConversationStatus, MessagingChannel, MessagingProviderName
from app.messaging.normalizer import detect_channel, normalize_phone_number
from app.messaging.providers.twilio_provider import TwilioMessagingProvider, TwilioSendError
from app.messaging.schemas import NormalizedInboundMessage
from app.messaging.services.conversation_service import ConversationService
from app.messaging.services.inbound_message_service import InboundMessageService
from app.messaging.services.outbound_message_service import OutboundMessageService
from app.models import Contact, Conversation, Message, MessageDirection, MessageRole


def test_sms_webhook_normalization():
    settings = Settings(twilio_account_sid="ACxxx", twilio_auth_token="token")
    provider = TwilioMessagingProvider(settings)
    inbound = provider.normalize_inbound(
        {
            "MessageSid": "SM111",
            "From": "+15551234567",
            "To": "+15557654321",
            "Body": "Hello SMS",
            "NumMedia": "0",
        }
    )
    assert inbound.channel is MessagingChannel.SMS
    assert inbound.message_id == "SM111"
    assert inbound.from_number.startswith("+")
    assert inbound.text == "Hello SMS"


def test_whatsapp_webhook_normalization():
    settings = Settings(twilio_account_sid="ACxxx", twilio_auth_token="token")
    provider = TwilioMessagingProvider(settings)
    inbound = provider.normalize_inbound(
        {
            "MessageSid": "SM222",
            "From": "whatsapp:+923001234567",
            "To": "whatsapp:+14155238886",
            "Body": "Salam",
            "NumMedia": "0",
        }
    )
    assert inbound.channel is MessagingChannel.WHATSAPP
    assert inbound.from_number == "+923001234567"
    assert inbound.to_number.startswith("+")


def test_channel_detection():
    assert detect_channel("+15551234567", "+15557654321") is MessagingChannel.SMS
    assert detect_channel("whatsapp:+92300", "whatsapp:+1415") is MessagingChannel.WHATSAPP


def test_phone_normalization_e164():
    assert normalize_phone_number("whatsapp:+923001234567") == "+923001234567"
    assert normalize_phone_number("+1 (555) 123-4567") == "+15551234567"


@pytest.mark.asyncio
async def test_contact_creation_and_reuse(db_session, tenant_id):
    service = ConversationService(db_session)
    contact1, created1 = await service.get_or_create_contact(
        tenant_id=tenant_id, phone_number="+923001111111", name="Ali"
    )
    contact2, created2 = await service.get_or_create_contact(
        tenant_id=tenant_id, phone_number="+923001111111"
    )
    assert created1 is True
    assert created2 is False
    assert contact1.id == contact2.id


@pytest.mark.asyncio
async def test_conversation_creation_and_active_reuse(db_session, tenant_id):
    service = ConversationService(db_session)
    contact, _ = await service.get_or_create_contact(
        tenant_id=tenant_id, phone_number="+923002222222"
    )
    conv1, created1 = await service.get_or_create_active_conversation(
        tenant_id=tenant_id, contact=contact, channel=MessagingChannel.SMS
    )
    conv2, created2 = await service.get_or_create_active_conversation(
        tenant_id=tenant_id, contact=contact, channel=MessagingChannel.SMS
    )
    assert created1 is True
    assert created2 is False
    assert conv1.id == conv2.id
    assert conv1.status is ConversationStatus.ACTIVE


@pytest.mark.asyncio
async def test_inbound_message_saved_and_duplicate_sid(db_session, tenant_id):
    settings = Settings(
        openai_api_key="",
        twilio_account_sid="ACxxx",
        twilio_auth_token="token",
        twilio_sms_from_number="+15557654321",
    )
    provider = MagicMock()
    provider.name = "twilio"
    provider.send_text = AsyncMock(
        return_value=SimpleNamespace(
            provider_message_sid="SMout1",
            provider_status="queued",
            channel=MessagingChannel.SMS,
        )
    )

    service = InboundMessageService(db_session, settings=settings, provider=provider)
    inbound = NormalizedInboundMessage(
        provider=MessagingProviderName.TWILIO,
        channel=MessagingChannel.SMS,
        message_id="SMin1",
        from_number="+923003333333",
        to_number="+15557654321",
        text="Need a flat",
    )
    first = await service.process_inbound(tenant_id=tenant_id, inbound=inbound)
    second = await service.process_inbound(tenant_id=tenant_id, inbound=inbound)

    assert first["ok"] is True
    assert second["duplicate"] is True

    result = await db_session.execute(select(Message).where(Message.provider_message_sid == "SMin1"))
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].direction is MessageDirection.INBOUND


@pytest.mark.asyncio
async def test_ai_disabled_prevents_auto_response(db_session, tenant_id):
    settings = Settings(openai_api_key="sk-test", twilio_sms_from_number="+15557654321")
    provider = MagicMock()
    provider.name = "twilio"
    provider.send_text = AsyncMock()

    conversations = ConversationService(db_session)
    contact, _ = await conversations.get_or_create_contact(
        tenant_id=tenant_id, phone_number="+923004444444"
    )
    conversation, _ = await conversations.get_or_create_active_conversation(
        tenant_id=tenant_id, contact=contact, channel=MessagingChannel.WHATSAPP
    )
    conversation.ai_enabled = False
    await db_session.flush()

    service = InboundMessageService(db_session, settings=settings, provider=provider)
    inbound = NormalizedInboundMessage(
        provider=MessagingProviderName.TWILIO,
        channel=MessagingChannel.WHATSAPP,
        message_id="SMin2",
        from_number="+923004444444",
        to_number="+14155238886",
        text="Hello human",
    )
    result = await service.process_inbound(tenant_id=tenant_id, inbound=inbound)
    assert result["ai_replied"] is False
    assert result["reason"] == "ai_disabled"
    provider.send_text.assert_not_called()


@pytest.mark.asyncio
async def test_outbound_sms_uses_sms_sender():
    settings = Settings(
        twilio_account_sid="ACxxx",
        twilio_auth_token="token",
        twilio_sms_from_number="+15557654321",
        twilio_whatsapp_from="whatsapp:+14155238886",
    )
    provider = TwilioMessagingProvider(settings)
    fake_message = SimpleNamespace(sid="SMout-sms", status="queued")
    provider._client = MagicMock()
    provider._client.messages.create.return_value = fake_message

    result = await provider.send_text(
        to_number="+923005555555",
        body="hi",
        channel=MessagingChannel.SMS,
    )
    kwargs = provider._client.messages.create.call_args.kwargs
    assert kwargs["from_"] == "+15557654321"
    assert kwargs["to"] == "+923005555555"
    assert result.channel is MessagingChannel.SMS


@pytest.mark.asyncio
async def test_outbound_whatsapp_uses_whatsapp_sender():
    settings = Settings(
        twilio_account_sid="ACxxx",
        twilio_auth_token="token",
        twilio_sms_from_number="+15557654321",
        twilio_whatsapp_from="+14155238886",
    )
    provider = TwilioMessagingProvider(settings)
    fake_message = SimpleNamespace(sid="SMout-wa", status="queued")
    provider._client = MagicMock()
    provider._client.messages.create.return_value = fake_message

    result = await provider.send_text(
        to_number="+923006666666",
        body="salam",
        channel=MessagingChannel.WHATSAPP,
    )
    kwargs = provider._client.messages.create.call_args.kwargs
    assert kwargs["from_"] == "whatsapp:+14155238886"
    assert kwargs["to"] == "whatsapp:+923006666666"
    assert result.channel is MessagingChannel.WHATSAPP


def test_invalid_twilio_signature_rejected():
    settings = Settings(
        app_env="production",
        twilio_account_sid="ACxxx",
        twilio_auth_token="secret-token",
    )
    provider = TwilioMessagingProvider(settings)
    ok = provider.validate_webhook(
        url="https://example.com/api/v1/messaging/twilio/inbound",
        params={"MessageSid": "SM1", "From": "+1", "To": "+2", "Body": "x"},
        signature="invalid",
    )
    assert ok is False


@pytest.mark.asyncio
async def test_twilio_failure_handled(db_session, tenant_id):
    settings = Settings(
        openai_api_key="",
        twilio_account_sid="ACxxx",
        twilio_auth_token="token",
        twilio_sms_from_number="+15557654321",
    )
    provider = MagicMock()
    provider.name = "twilio"
    provider.send_text = AsyncMock(side_effect=TwilioSendError("provider down"))

    service = InboundMessageService(db_session, settings=settings, provider=provider)
    inbound = NormalizedInboundMessage(
        provider=MessagingProviderName.TWILIO,
        channel=MessagingChannel.SMS,
        message_id="SMin3",
        from_number="+923007777777",
        to_number="+15557654321",
        text="Are you there?",
    )
    result = await service.process_inbound(tenant_id=tenant_id, inbound=inbound)
    assert result["ok"] is True
    assert result["ai_replied"] is False
    assert result["reason"] == "twilio_send_failure"

    saved = await db_session.execute(select(Message).where(Message.provider_message_sid == "SMin3"))
    assert saved.scalar_one().role is MessageRole.USER


@pytest.mark.asyncio
async def test_outbound_service_persists_message(db_session, tenant_id):
    settings = Settings(twilio_sms_from_number="+15557654321")
    provider = MagicMock()
    provider.name = "twilio"
    provider.send_text = AsyncMock(
        return_value=SimpleNamespace(
            provider_message_sid="SMout9",
            provider_status="sent",
            channel=MessagingChannel.SMS,
        )
    )
    conversations = ConversationService(db_session)
    contact, _ = await conversations.get_or_create_contact(
        tenant_id=tenant_id, phone_number="+923008888888"
    )
    conversation, _ = await conversations.get_or_create_active_conversation(
        tenant_id=tenant_id, contact=contact, channel=MessagingChannel.SMS
    )
    outbound = OutboundMessageService(db_session, settings=settings, provider=provider)
    message = await outbound.send_message(
        contact=contact,
        conversation=conversation,
        text="Reply body",
        channel=MessagingChannel.SMS,
    )
    assert message.provider_message_sid == "SMout9"
    assert message.direction is MessageDirection.OUTBOUND
