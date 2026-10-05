from __future__ import annotations

import logging
import time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.text_agent import (
    HISTORY_LIMIT,
    build_known_facts,
    chunk_outbound_text,
    merge_conversation_state,
    stream_text_agent_reply,
)
from app.config import Settings, get_settings
from app.messaging.enums import MessageDirection, MessageRole, MessagingProviderName
from app.messaging.providers.base import MessagingProvider
from app.messaging.schemas import NormalizedInboundMessage, TextAgentContext
from app.messaging.services.conversation_service import ConversationService
from app.messaging.services.outbound_message_service import OutboundMessageService
from app.messaging.stream_hub import stream_hub
from app.models import Contact, Conversation, Message
from app.schemas import MessageOut

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
        accepted = await self.accept_inbound(tenant_id=tenant_id, inbound=inbound)
        if accepted.get("duplicate") or not accepted.get("should_ai_reply"):
            return accepted

        return await self.generate_and_send_reply(
            tenant_id=tenant_id,
            conversation_id=UUID(accepted["conversation_id"]),
            inbound_message_id=UUID(accepted["inbound_message_id"]),
            status_callback_url=status_callback_url,
        )

    async def accept_inbound(
        self,
        *,
        tenant_id: UUID,
        inbound: NormalizedInboundMessage,
    ) -> dict:
        """Persist inbound message quickly; optionally defer AI generation."""
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
        conversation, created_conversation = await self._conversations.get_or_create_active_conversation(
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
        meta = dict(conversation.metadata_json or {})
        meta["unread_count"] = int(meta.get("unread_count") or 0) + 1

        prior_state = meta.get("conversation_state")
        if not isinstance(prior_state, dict):
            prior_state = {}
        meta["conversation_state"] = merge_conversation_state(prior_state, body)
        conversation.metadata_json = meta
        await self._db.flush()

        logger.info(
            "MESSAGE_SAVED direction=inbound conversation_id=%s message_sid=%s",
            conversation.id,
            inbound.message_id,
        )

        await stream_hub.publish_inbound(
            conversation.id,
            message=MessageOut.model_validate(inbound_message).model_dump(mode="json"),
        )

        if not body.strip():
            return {
                "ok": True,
                "ai_replied": False,
                "should_ai_reply": False,
                "reason": "empty_body",
                "conversation_id": str(conversation.id),
                "inbound_message_id": str(inbound_message.id),
            }

        if not conversation.ai_enabled:
            logger.info(
                "AI_REPLY_SKIPPED reason=ai_disabled conversation_id=%s",
                conversation.id,
            )
            return {
                "ok": True,
                "ai_replied": False,
                "should_ai_reply": False,
                "reason": "ai_disabled",
                "conversation_id": str(conversation.id),
                "inbound_message_id": str(inbound_message.id),
            }

        meta["ai_generation"] = {
            "inbound_sid": inbound.message_id,
            "inbound_message_id": str(inbound_message.id),
            "status": "pending",
            "is_new_conversation": created_conversation
            or int(meta.get("message_count_hint") or 0) <= 1,
        }
        meta["message_count_hint"] = int(meta.get("message_count_hint") or 0) + 1
        conversation.metadata_json = meta
        await self._db.flush()

        return {
            "ok": True,
            "should_ai_reply": True,
            "conversation_id": str(conversation.id),
            "inbound_message_id": str(inbound_message.id),
            "channel": inbound.channel.value,
        }

    async def generate_and_send_reply(
        self,
        *,
        tenant_id: UUID,
        conversation_id: UUID,
        inbound_message_id: UUID,
        status_callback_url: str | None = None,
    ) -> dict:
        conversation = await self._db.get(Conversation, conversation_id)
        inbound_message = await self._db.get(Message, inbound_message_id)
        if conversation is None or inbound_message is None:
            return {"ok": False, "reason": "missing_records"}
        if conversation.tenant_id != tenant_id:
            return {"ok": False, "reason": "tenant_mismatch"}

        if not conversation.ai_enabled:
            return {
                "ok": True,
                "ai_replied": False,
                "reason": "ai_disabled",
                "conversation_id": str(conversation.id),
            }

        meta = dict(conversation.metadata_json or {})
        generation = dict(meta.get("ai_generation") or {})
        if generation.get("inbound_message_id") == str(inbound_message_id):
            if generation.get("status") == "completed":
                return {
                    "ok": True,
                    "ai_replied": True,
                    "duplicate": True,
                    "conversation_id": str(conversation.id),
                }
            if generation.get("status") == "started":
                return {
                    "ok": True,
                    "ai_replied": False,
                    "reason": "generation_in_progress",
                    "conversation_id": str(conversation.id),
                }

        generation["status"] = "started"
        generation["inbound_message_id"] = str(inbound_message_id)
        meta["ai_generation"] = generation
        conversation.metadata_json = meta
        await self._db.flush()

        contact = await self._db.get(Contact, conversation.contact_id)
        if contact is None:
            return {"ok": False, "reason": "missing_contact"}

        history = await self._conversations.get_conversation_history(
            conversation.id, limit=HISTORY_LIMIT + 1
        )
        state = meta.get("conversation_state")
        if not isinstance(state, dict):
            state = {}
        known_facts = build_known_facts(
            contact=contact,
            conversation=conversation,
            conversation_state=state,
        )
        is_new = bool(generation.get("is_new_conversation"))
        # Heuristic: only treat as new if very few prior messages.
        if len(history) > 2:
            is_new = False

        context = TextAgentContext(
            contact_id=contact.id,
            contact_name=contact.name,
            phone_number=contact.phone_number,
            preferred_language=contact.preferred_language.value,
            conversation_id=conversation.id,
            channel=conversation.channel,
            history=history,
            latest_user_message=inbound_message.body,
            known_facts=known_facts,
            is_new_conversation=is_new,
        )

        logger.info(
            "AI_REPLY_REQUESTED conversation_id=%s channel=%s",
            conversation.id,
            conversation.channel.value,
        )
        await stream_hub.publish_start(
            conversation.id,
            inbound_message_id=str(inbound_message.id),
        )

        full_text = ""
        try:
            async for delta in stream_text_agent_reply(
                contact=contact,
                conversation=conversation,
                incoming_message=inbound_message,
                context=context,
                settings=self._settings,
            ):
                full_text += delta
                await stream_hub.publish_delta(conversation.id, text=delta)
        except Exception:
            logger.exception(
                "AI_REPLY_FAILED conversation_id=%s channel=%s",
                conversation.id,
                conversation.channel.value,
            )
            generation["status"] = "failed"
            meta["ai_generation"] = generation
            conversation.metadata_json = meta
            await self._db.flush()
            await stream_hub.publish_error(conversation.id, reason="openai_failure")
            return {
                "ok": True,
                "ai_replied": False,
                "reason": "openai_failure",
                "conversation_id": str(conversation.id),
            }

        reply_text = full_text.strip()
        if not reply_text:
            generation["status"] = "failed"
            meta["ai_generation"] = generation
            conversation.metadata_json = meta
            await self._db.flush()
            await stream_hub.publish_error(conversation.id, reason="empty_reply")
            return {
                "ok": True,
                "ai_replied": False,
                "reason": "empty_reply",
                "conversation_id": str(conversation.id),
            }

        logger.info("AI_REPLY_GENERATED conversation_id=%s", conversation.id)
        chunks = chunk_outbound_text(reply_text, channel=conversation.channel)
        outbound_ids: list[str] = []
        last_outbound: Message | None = None

        send_started = time.perf_counter()
        logger.info(
            "TEXT_AGENT_PROVIDER_SEND_STARTED conversation_id=%s chunks=%d",
            conversation.id,
            len(chunks),
        )
        try:
            for chunk in chunks:
                outbound = await self._outbound.send_message(
                    contact=contact,
                    conversation=conversation,
                    text=chunk,
                    channel=conversation.channel,
                    role=MessageRole.ASSISTANT,
                    status_callback_url=status_callback_url,
                )
                outbound_ids.append(str(outbound.id))
                last_outbound = outbound
        except Exception:
            logger.exception(
                "OUTBOUND_MESSAGE_FAILED conversation_id=%s channel=%s",
                conversation.id,
                conversation.channel.value,
            )
            generation["status"] = "failed"
            meta["ai_generation"] = generation
            conversation.metadata_json = meta
            await self._db.flush()
            await stream_hub.publish_error(conversation.id, reason="twilio_send_failure")
            return {
                "ok": True,
                "ai_replied": False,
                "reason": "twilio_send_failure",
                "conversation_id": str(conversation.id),
            }

        logger.info(
            "TEXT_AGENT_PROVIDER_SEND_COMPLETED conversation_id=%s ms=%d",
            conversation.id,
            int((time.perf_counter() - send_started) * 1000),
        )

        generation["status"] = "completed"
        generation["outbound_message_ids"] = outbound_ids
        meta["ai_generation"] = generation
        conversation.metadata_json = meta
        await self._db.flush()

        if last_outbound is not None:
            # Dashboard sees the full accumulated reply on done (not per-chunk spam).
            await stream_hub.publish_done(
                conversation.id,
                message_id=str(last_outbound.id),
                body=reply_text,
            )
            logger.info(
                "MESSAGE_SAVED direction=outbound conversation_id=%s message_sid=%s",
                conversation.id,
                last_outbound.provider_message_sid,
            )

        return {
            "ok": True,
            "ai_replied": True,
            "conversation_id": str(conversation.id),
            "inbound_message_id": str(inbound_message.id),
            "outbound_message_id": outbound_ids[-1] if outbound_ids else None,
            "outbound_message_ids": outbound_ids,
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
    allowed = {
        "AccountSid",
        "MessagingServiceSid",
        "NumMedia",
        "SmsStatus",
        "FromCity",
        "FromCountry",
    }
    return {key: raw.get(key) for key in allowed if key in raw}
