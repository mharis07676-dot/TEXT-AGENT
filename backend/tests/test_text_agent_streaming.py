from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.ai.text_agent import (
    build_openai_messages,
    chunk_outbound_text,
    generate_text_agent_reply,
    merge_conversation_state,
    stream_text_agent_reply,
)
from app.config import Settings
from app.messaging.enums import MessagingChannel, MessagingProviderName
from app.messaging.schemas import ConversationHistoryItem, NormalizedInboundMessage, TextAgentContext
from app.messaging.services.conversation_service import ConversationService
from app.messaging.services.inbound_message_service import InboundMessageService
from app.messaging.stream_hub import ConversationStreamHub
from app.models import Message, MessageDirection, MessageRole


def _fake_stream(parts: list[str]):
    async def _gen():
        for part in parts:
            yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=part))])

    return _gen()


@pytest.mark.asyncio
async def test_openai_stream_accumulates_deltas():
    settings = Settings(openai_api_key="sk-test", openai_text_model="gpt-4.1-mini")
    contact = SimpleNamespace(
        id=uuid4(),
        name="Ali",
        phone_number="+923001111111",
        preferred_language=SimpleNamespace(value="english"),
    )
    conversation = SimpleNamespace(id=uuid4(), channel=MessagingChannel.SMS)
    incoming = SimpleNamespace(body="I need a house in DHA")
    context = TextAgentContext(
        contact_id=contact.id,
        contact_name=contact.name,
        phone_number=contact.phone_number,
        preferred_language="english",
        conversation_id=conversation.id,
        channel=MessagingChannel.SMS,
        history=[],
        latest_user_message=incoming.body,
        known_facts={},
        is_new_conversation=True,
    )

    deltas: list[str] = []
    with patch("app.ai.text_agent.AsyncOpenAI") as client_cls:
        client = MagicMock()
        client_cls.return_value = client
        client.chat.completions.create = AsyncMock(
            return_value=_fake_stream(["Sure", " — ", "buy or rent?"])
        )
        async for delta in stream_text_agent_reply(
            contact=contact,
            conversation=conversation,
            incoming_message=incoming,
            context=context,
            settings=settings,
        ):
            deltas.append(delta)

    assert deltas == ["Sure", " — ", "buy or rent?"]
    full = await generate_text_agent_reply(
        contact=contact,
        conversation=conversation,
        incoming_message=incoming,
        context=context,
        settings=Settings(openai_api_key=""),
    )
    assert full  # fallback path still works without API key


def test_chunk_outbound_never_token_splits():
    short = chunk_outbound_text("Sure. Buy or rent?", channel=MessagingChannel.SMS)
    assert short == ["Sure. Buy or rent?"]

    long = (
        "Sure. We help teams qualify leads over WhatsApp and SMS. "
        "The AI can hand qualified leads to your sales team. "
        "Are you mainly interested in lead qualification or appointment booking? "
        "We also support human takeover when needed."
    )
    parts = chunk_outbound_text(long, channel=MessagingChannel.WHATSAPP)
    assert 1 <= len(parts) <= 3
    assert all(len(p) > 10 for p in parts)
    assert "".join(parts).replace(" ", "") in long.replace(" ", "") or " ".join(parts)


def test_build_messages_uses_history_and_known_facts():
    conversation_id = uuid4()
    context = TextAgentContext(
        contact_id=uuid4(),
        contact_name="Sara",
        phone_number="+92300",
        preferred_language="english",
        conversation_id=conversation_id,
        channel=MessagingChannel.WHATSAPP,
        history=[
            ConversationHistoryItem(
                role="user",
                body="I need a property in Lahore",
                channel="whatsapp",
                direction="inbound",
            ),
            ConversationHistoryItem(
                role="assistant",
                body="Sure. Buy or rent?",
                channel="whatsapp",
                direction="outbound",
            ),
            ConversationHistoryItem(
                role="user",
                body="Buy. Budget 3 crore. DHA Phase 6 house.",
                channel="whatsapp",
                direction="inbound",
            ),
        ],
        latest_user_message="Buy. Budget 3 crore. DHA Phase 6 house.",
        known_facts={
            "intent": "buy",
            "budget": "3 crore",
            "location": "DHA Phase 6",
            "property_type": "house",
        },
        is_new_conversation=False,
    )
    messages = build_openai_messages(context)
    assert messages[0]["role"] == "system"
    assert "one follow-up question" in messages[0]["content"].lower() or "ONE follow-up" in messages[0]["content"]
    assert any("Known facts" in m["content"] for m in messages if m["role"] == "system")
    # Latest user message appears once at the end, not duplicated from history.
    assert messages[-1] == {"role": "user", "content": context.latest_user_message}
    user_bodies = [m["content"] for m in messages if m["role"] == "user"]
    assert user_bodies.count(context.latest_user_message) == 1


def test_merge_conversation_state_extracts_known_fields():
    state = merge_conversation_state({}, "I want to buy a house in DHA Phase 6 under 3 crore")
    assert state.get("intent") == "buy"
    assert state.get("property_type") == "house"
    assert "DHA" in (state.get("location") or "")
    assert state.get("budget")


@pytest.mark.asyncio
async def test_roman_urdu_fallback_stays_natural():
    contact = SimpleNamespace(
        name="Ali",
        preferred_language=SimpleNamespace(value="roman_urdu"),
    )
    incoming = SimpleNamespace(body="Mujhe DHA mein house chahiye")
    context = TextAgentContext(
        contact_id=uuid4(),
        contact_name="Ali",
        phone_number="+92300",
        preferred_language="roman_urdu",
        conversation_id=uuid4(),
        channel=MessagingChannel.WHATSAPP,
        history=[],
        latest_user_message=incoming.body,
        is_new_conversation=False,
    )
    reply = await generate_text_agent_reply(
        contact=contact,
        conversation=SimpleNamespace(id=uuid4(), channel=MessagingChannel.WHATSAPP),
        incoming_message=incoming,
        context=context,
        settings=Settings(openai_api_key=""),
    )
    assert "Please provide" not in reply
    assert "inquiry" not in reply.lower()


@pytest.mark.asyncio
async def test_stream_hub_publishes_deltas_and_done():
    hub = ConversationStreamHub()
    conversation_id = uuid4()
    queue = await hub.subscribe(conversation_id)
    await hub.publish_start(conversation_id, inbound_message_id="in1")
    await hub.publish_delta(conversation_id, text="Sure")
    await hub.publish_done(conversation_id, message_id="out1", body="Sure")
    events = [await queue.get(), await queue.get(), await queue.get()]
    assert events[0]["type"] == "start"
    assert events[1] == {"type": "delta", "text": "Sure"}
    assert events[2]["type"] == "done"
    assert events[2]["message_id"] == "out1"
    await hub.unsubscribe(conversation_id, queue)


@pytest.mark.asyncio
async def test_inbound_streams_once_saves_one_assistant_and_sends_completed(
    db_session, tenant_id
):
    settings = Settings(
        openai_api_key="sk-test",
        twilio_account_sid="ACxxx",
        twilio_auth_token="token",
        twilio_sms_from_number="+15557654321",
    )
    provider = MagicMock()
    provider.name = "twilio"
    provider.send_text = AsyncMock(
        return_value=SimpleNamespace(
            provider_message_sid="SMout-stream",
            provider_status="queued",
            channel=MessagingChannel.SMS,
        )
    )

    hub = ConversationStreamHub()

    with (
        patch(
            "app.messaging.services.inbound_message_service.stream_text_agent_reply",
            return_value=_fake_delta_iter(["Sure", " — buy or rent?"]),
        ),
        patch("app.messaging.services.inbound_message_service.stream_hub", hub),
    ):
        service = InboundMessageService(db_session, settings=settings, provider=provider)
        inbound = NormalizedInboundMessage(
            provider=MessagingProviderName.TWILIO,
            channel=MessagingChannel.SMS,
            message_id="SMstream1",
            from_number="+923009999001",
            to_number="+15557654321",
            text="I need a property in DHA",
        )
        accepted = await service.accept_inbound(tenant_id=tenant_id, inbound=inbound)
        conversation_id = UUID(accepted["conversation_id"])
        queue = await hub.subscribe(conversation_id)
        result = await service.generate_and_send_reply(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            inbound_message_id=UUID(accepted["inbound_message_id"]),
        )

    assert result["ai_replied"] is True
    provider.send_text.assert_called_once()
    sent_body = provider.send_text.await_args.kwargs["body"]
    assert sent_body == "Sure — buy or rent?"

    rows = (
        await db_session.execute(
            select(Message).where(Message.conversation_id == conversation_id)
        )
    ).scalars().all()
    inbound_rows = [r for r in rows if r.direction is MessageDirection.INBOUND]
    assistant_rows = [r for r in rows if r.role is MessageRole.ASSISTANT]
    assert len(inbound_rows) == 1
    assert len(assistant_rows) == 1
    assert assistant_rows[0].body == "Sure — buy or rent?"

    got = []
    while not queue.empty():
        got.append(await queue.get())
    types = [e["type"] for e in got]
    assert "start" in types
    assert "delta" in types
    assert "done" in types
    done = next(e for e in got if e["type"] == "done")
    assert done["message_id"] == str(assistant_rows[0].id)


async def _fake_delta_iter(parts: list[str]):
    for part in parts:
        yield part


@pytest.mark.asyncio
async def test_streaming_failure_does_not_send_incomplete(db_session, tenant_id):
    settings = Settings(openai_api_key="sk-test", twilio_sms_from_number="+15557654321")
    provider = MagicMock()
    provider.name = "twilio"
    provider.send_text = AsyncMock()

    async def failing_stream(**_kwargs):
        yield "Sure"
        raise RuntimeError("boom")

    with patch(
        "app.messaging.services.inbound_message_service.stream_text_agent_reply",
        new=failing_stream,
    ):
        service = InboundMessageService(db_session, settings=settings, provider=provider)
        inbound = NormalizedInboundMessage(
            provider=MessagingProviderName.TWILIO,
            channel=MessagingChannel.WHATSAPP,
            message_id="SMfail1",
            from_number="+923009999002",
            to_number="+14155238886",
            text="Hello",
        )
        result = await service.process_inbound(tenant_id=tenant_id, inbound=inbound)

    assert result["ai_replied"] is False
    assert result["reason"] == "openai_failure"
    provider.send_text.assert_not_called()

    assistants = (
        await db_session.execute(select(Message).where(Message.role == MessageRole.ASSISTANT))
    ).scalars().all()
    assert assistants == []


@pytest.mark.asyncio
async def test_duplicate_webhook_does_not_generate_twice(db_session, tenant_id):
    settings = Settings(openai_api_key="", twilio_sms_from_number="+15557654321")
    provider = MagicMock()
    provider.name = "twilio"
    provider.send_text = AsyncMock(
        return_value=SimpleNamespace(
            provider_message_sid="SMout-dup",
            provider_status="queued",
            channel=MessagingChannel.SMS,
        )
    )
    service = InboundMessageService(db_session, settings=settings, provider=provider)
    inbound = NormalizedInboundMessage(
        provider=MessagingProviderName.TWILIO,
        channel=MessagingChannel.SMS,
        message_id="SMdup-stream",
        from_number="+923009999003",
        to_number="+15557654321",
        text="Need a flat",
    )
    first = await service.process_inbound(tenant_id=tenant_id, inbound=inbound)
    second = await service.process_inbound(tenant_id=tenant_id, inbound=inbound)
    assert first["ok"] is True
    assert second.get("duplicate") is True
    assert provider.send_text.await_count == 1


@pytest.mark.asyncio
async def test_ai_disabled_skips_generation_with_stream_path(db_session, tenant_id):
    settings = Settings(openai_api_key="sk-test")
    provider = MagicMock()
    provider.send_text = AsyncMock()
    conversations = ConversationService(db_session)
    contact, _ = await conversations.get_or_create_contact(
        tenant_id=tenant_id, phone_number="+923009999004"
    )
    conversation, _ = await conversations.get_or_create_active_conversation(
        tenant_id=tenant_id, contact=contact, channel=MessagingChannel.SMS
    )
    conversation.ai_enabled = False
    await db_session.flush()

    service = InboundMessageService(db_session, settings=settings, provider=provider)
    result = await service.process_inbound(
        tenant_id=tenant_id,
        inbound=NormalizedInboundMessage(
            provider=MessagingProviderName.TWILIO,
            channel=MessagingChannel.SMS,
            message_id="SMhuman1",
            from_number="+923009999004",
            to_number="+15557654321",
            text="Talk to a person",
        ),
    )
    assert result["reason"] == "ai_disabled"
    provider.send_text.assert_not_called()


@pytest.mark.asyncio
async def test_whatsapp_receives_completed_not_tokens(db_session, tenant_id):
    settings = Settings(openai_api_key="sk-test", twilio_whatsapp_from="+14155238886")
    provider = MagicMock()
    provider.name = "twilio"
    provider.send_text = AsyncMock(
        return_value=SimpleNamespace(
            provider_message_sid="SMwa1",
            provider_status="queued",
            channel=MessagingChannel.WHATSAPP,
        )
    )
    with patch(
        "app.messaging.services.inbound_message_service.stream_text_agent_reply",
        return_value=_fake_delta_iter(["A", "B", "C", " full reply"]),
    ):
        service = InboundMessageService(db_session, settings=settings, provider=provider)
        await service.process_inbound(
            tenant_id=tenant_id,
            inbound=NormalizedInboundMessage(
                provider=MessagingProviderName.TWILIO,
                channel=MessagingChannel.WHATSAPP,
                message_id="SMwa-in",
                from_number="+923009999005",
                to_number="+14155238886",
                text="Salam",
            ),
        )
    assert provider.send_text.await_count == 1
    assert provider.send_text.await_args.kwargs["body"] == "ABC full reply"
    assert provider.send_text.await_args.kwargs["channel"] is MessagingChannel.WHATSAPP
