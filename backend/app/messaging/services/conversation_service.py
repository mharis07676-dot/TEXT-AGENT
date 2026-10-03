from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.messaging.enums import ConversationStatus, MessagingChannel
from app.messaging.schemas import ConversationHistoryItem
from app.models import Contact, Conversation, Message

logger = logging.getLogger(__name__)


class ConversationService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_or_create_contact(
        self,
        *,
        tenant_id: UUID,
        phone_number: str,
        name: str | None = None,
    ) -> tuple[Contact, bool]:
        result = await self._db.execute(
            select(Contact).where(
                Contact.tenant_id == tenant_id,
                Contact.phone_number == phone_number,
            )
        )
        contact = result.scalar_one_or_none()
        if contact is not None:
            logger.info(
                "CONTACT_FOUND contact_id=%s phone=%s",
                contact.id,
                _mask_phone(phone_number),
            )
            return contact, False

        contact = Contact(
            tenant_id=tenant_id,
            phone_number=phone_number,
            name=name,
            metadata_json={},
        )
        self._db.add(contact)
        await self._db.flush()
        logger.info(
            "CONTACT_CREATED contact_id=%s phone=%s",
            contact.id,
            _mask_phone(phone_number),
        )
        return contact, True

    async def get_or_create_active_conversation(
        self,
        *,
        tenant_id: UUID,
        contact: Contact,
        channel: MessagingChannel,
    ) -> tuple[Conversation, bool]:
        result = await self._db.execute(
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.contact_id == contact.id,
                Conversation.channel == channel,
                Conversation.status == ConversationStatus.ACTIVE,
            )
            .order_by(Conversation.created_at.desc())
            .limit(1)
        )
        conversation = result.scalar_one_or_none()
        if conversation is not None:
            logger.info(
                "CONVERSATION_FOUND conversation_id=%s channel=%s",
                conversation.id,
                channel.value,
            )
            return conversation, False

        conversation = Conversation(
            tenant_id=tenant_id,
            contact_id=contact.id,
            channel=channel,
            status=ConversationStatus.ACTIVE,
            ai_enabled=True,
            metadata_json={},
        )
        self._db.add(conversation)
        await self._db.flush()
        logger.info(
            "CONVERSATION_CREATED conversation_id=%s channel=%s",
            conversation.id,
            channel.value,
        )
        return conversation, True

    async def touch_last_message_at(self, conversation: Conversation) -> None:
        conversation.last_message_at = datetime.now(timezone.utc)
        conversation.updated_at = datetime.now(timezone.utc)
        await self._db.flush()

    async def get_conversation_history(
        self,
        conversation_id: UUID,
        *,
        limit: int = 20,
    ) -> list[ConversationHistoryItem]:
        result = await self._db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        rows = list(result.scalars().all())
        rows.reverse()
        return [
            ConversationHistoryItem(
                role=row.role.value if hasattr(row.role, "value") else str(row.role),
                body=row.body,
                channel=row.channel.value if hasattr(row.channel, "value") else str(row.channel),
                direction=row.direction.value if hasattr(row.direction, "value") else str(row.direction),
                created_at=row.created_at.isoformat() if row.created_at else None,
            )
            for row in rows
        ]


def _mask_phone(phone: str) -> str:
    if len(phone) <= 4:
        return "****"
    return f"{phone[:3]}***{phone[-2:]}"
