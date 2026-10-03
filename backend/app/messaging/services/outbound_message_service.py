from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.messaging.dispatcher import get_messaging_provider
from app.messaging.enums import MessageDirection, MessageRole, MessagingChannel, MessagingProviderName
from app.messaging.providers.base import MessagingProvider
from app.messaging.providers.twilio_provider import TwilioSendError
from app.messaging.services.conversation_service import ConversationService
from app.models import Contact, Conversation, Message

logger = logging.getLogger(__name__)


class OutboundMessageService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        settings: Settings | None = None,
        provider: MessagingProvider | None = None,
    ) -> None:
        self._db = db
        self._settings = settings or get_settings()
        self._provider = provider or get_messaging_provider(self._settings)
        self._conversations = ConversationService(db)

    async def send_message(
        self,
        *,
        contact: Contact,
        conversation: Conversation,
        text: str,
        channel: MessagingChannel | None = None,
        role: MessageRole = MessageRole.ASSISTANT,
        status_callback_url: str | None = None,
    ) -> Message:
        resolved_channel = channel or conversation.channel
        try:
            result = await self._provider.send_text(
                to_number=contact.phone_number,
                body=text,
                channel=resolved_channel,
                status_callback_url=status_callback_url,
            )
        except TwilioSendError:
            logger.error(
                "OUTBOUND_MESSAGE_FAILED provider=%s channel=%s conversation_id=%s",
                self._provider.name,
                resolved_channel.value,
                conversation.id,
            )
            raise

        message = Message(
            tenant_id=conversation.tenant_id,
            conversation_id=conversation.id,
            role=role,
            direction=MessageDirection.OUTBOUND,
            channel=resolved_channel,
            body=text,
            provider=MessagingProviderName.TWILIO,
            provider_message_sid=result.provider_message_sid,
            provider_status=result.provider_status,
            metadata_json={},
        )
        self._db.add(message)
        await self._db.flush()
        await self._conversations.touch_last_message_at(conversation)

        logger.info(
            "OUTBOUND_MESSAGE_SENT provider=%s channel=%s conversation_id=%s message_sid=%s",
            self._provider.name,
            resolved_channel.value,
            conversation.id,
            result.provider_message_sid,
        )
        return message

    async def update_provider_status(
        self,
        *,
        provider_message_sid: str,
        provider_status: str,
        metadata: dict | None = None,
    ) -> Message | None:
        from sqlalchemy import select

        result = await self._db.execute(
            select(Message).where(Message.provider_message_sid == provider_message_sid)
        )
        message = result.scalar_one_or_none()
        if message is None:
            return None
        message.provider_status = provider_status
        if metadata:
            current = dict(message.metadata_json or {})
            current["status_callback"] = metadata
            message.metadata_json = current
        await self._db.flush()
        return message
