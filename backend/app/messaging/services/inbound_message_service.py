from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.text_agent import generate_text_agent_reply
from app.config import Settings, get_settings
from app.messaging.enums import MessageDirection, MessageRole, MessagingProviderName
from app.messaging.providers.base import MessagingProvider
from app.messaging.schemas import NormalizedInboundMessage, TextAgentContext
from app.messaging.services.conversation_service import ConversationService
from app.messaging.services.outbound_message_service import OutboundMessageService
from app.models import Message

logger = logging.getLogger(__name__)


class InboundMessageService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        settings: Settings | None = None,
        provider: MessagingProvider | None = None,
        outbound: OutboundMessageService | None = None,
    ) -> None:
        self._db = db
        self._settings = settings or get_settings()
        self._conversations = ConversationService(db)
        self._outbound = outbound or OutboundMessageService(
            db, settings=self._settings, provider=provider
        )

    async def process_inbound(
        self,
        *,
        tenant_id: UUID,
        inbound: NormalizedInboundMessage,
        status_callback_url: str | None = None,
    ) -> dict:
        logger.info(
            "INBOUND_MESSAGE_RECEIVED provider=%s channel=%s message_sid=%s",
            inbound.provider.value,
            inbound.channel.value,
            inbound.message_id,
        )

        existing = await self._find_by_provider_sid(inbound.message_id, inbound.provider)
        if existing is not None:
            logger.info(
                "WEBHOOK_DUPLICATE_SKIPPED provider=%s message_sid=%s",
                inbound.provider.value,
                inbound.message_id,
            )
            return {
                "ok": True,
                "duplicate": True,
                "conversation_id": str(existing.conversation_id),
                "message_id": str(existing.id),
            }

        contact, _ = await self._conversations.get_or_create_contact(
            tenant_id=tenant_id,
            phone_number=inbound.from_number,
        )
        conversation, _ = await self._conversations.get_or_create_active_conversation(
            tenant_id=tenant_id,
            contact=contact,
            channel=inbound.channel,
        )

        body = inbound.text or ""
        if len(body) > self._settings.max_inbound_message_chars:
            body = body[: self._settings.max_inbound_message_chars]

        inbound_message = Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            role=MessageRole.USER,
            direction=MessageDirection.INBOUND,
            channel=inbound.channel,
            body=body,
            provider=inbound.provider,
            provider_message_sid=inbound.message_id,
            provider_status="received",
            metadata_json={
                "media_urls": inbound.media_urls,
                "to_number": inbound.to_number,
                "raw": _safe_raw_metadata(inbound.raw_metadata),
            },
        )
        self._db.add(inbound_message)
        try:
            await self._db.flush()
        except IntegrityError:
            await self._db.rollback()
            logger.info(
                "WEBHOOK_DUPLICATE_SKIPPED provider=%s message_sid=%s",
                inbound.provider.value,
                inbound.message_id,
            )
            return {"ok": True, "duplicate": True}

        await self._conversations.touch_last_message_at(conversation)
        logger.info(
            "MESSAGE_SAVED direction=inbound conversation_id=%s message_sid=%s",
            conversation.id,
            inbound.message_id,
        )

        if not body.strip():
            return {
                "ok": True,
                "ai_replied": False,
                "reason": "empty_body",
                "conversation_id": str(conversation.id),
            }

        if not conversation.ai_enabled:
            logger.info(
                "AI_REPLY_SKIPPED reason=ai_disabled conversation_id=%s",
                conversation.id,
            )
            return {
                "ok": True,
                "ai_replied": False,
                "reason": "ai_disabled",
                "conversation_id": str(conversation.id),
            }

        history = await self._conversations.get_conversation_history(conversation.id, limit=20)
        context = TextAgentContext(
            contact_id=contact.id,
            contact_name=contact.name,
            phone_number=contact.phone_number,
            preferred_language=contact.preferred_language.value,
            conversation_id=conversation.id,
            channel=inbound.channel,
            history=history,
            latest_user_message=body,
        )

        logger.info("AI_REPLY_REQUESTED conversation_id=%s channel=%s", conversation.id, inbound.channel.value)
        try:
            reply_text = await generate_text_agent_reply(
                contact=contact,
                conversation=conversation,
                incoming_message=inbound_message,
                context=context,
                settings=self._settings,
            )
        except Exception:
            logger.exception(
                "AI_REPLY_FAILED conversation_id=%s channel=%s",
                conversation.id,
                inbound.channel.value,
            )
            return {
                "ok": True,
                "ai_replied": False,
                "reason": "openai_failure",
                "conversation_id": str(conversation.id),
            }

        logger.info("AI_REPLY_GENERATED conversation_id=%s", conversation.id)

        try:
            outbound = await self._outbound.send_message(
                contact=contact,
                conversation=conversation,
                text=reply_text,
                channel=inbound.channel,
                role=MessageRole.ASSISTANT,
                status_callback_url=status_callback_url,
            )
        except Exception:
            logger.exception(
                "OUTBOUND_MESSAGE_FAILED conversation_id=%s channel=%s",
                conversation.id,
                inbound.channel.value,
            )
            return {
                "ok": True,
                "ai_replied": False,
                "reason": "twilio_send_failure",
                "conversation_id": str(conversation.id),
            }

        logger.info(
            "MESSAGE_SAVED direction=outbound conversation_id=%s message_sid=%s",
            conversation.id,
            outbound.provider_message_sid,
        )
        return {
            "ok": True,
            "ai_replied": True,
            "conversation_id": str(conversation.id),
            "inbound_message_id": str(inbound_message.id),
            "outbound_message_id": str(outbound.id),
        }

    async def _find_by_provider_sid(
        self,
        provider_message_sid: str,
        provider: MessagingProviderName,
    ) -> Message | None:
        result = await self._db.execute(
            select(Message).where(
                Message.provider == provider,
                Message.provider_message_sid == provider_message_sid,
            )
        )
        return result.scalar_one_or_none()


def _safe_raw_metadata(raw: dict) -> dict:
    # Keep compact non-sensitive metadata only.
    allowed = {
        "AccountSid",
        "MessagingServiceSid",
        "NumMedia",
        "SmsStatus",
        "FromCity",
        "FromCountry",
    }
    return {key: raw.get(key) for key in allowed if key in raw}
