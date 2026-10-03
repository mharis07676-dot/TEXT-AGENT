from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Query, Request, Response
from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import AuthContext, get_current_auth
from app.config import get_settings
from app.db.session import get_db
from app.messaging.dispatcher import get_messaging_provider
from app.messaging.enums import ConversationStatus, MessageDirection, MessageRole, MessagingChannel
from app.messaging.providers.twilio_provider import TwilioSendError
from app.messaging.schemas import MessagingHealthOut
from app.messaging.services.inbound_message_service import InboundMessageService
from app.messaging.services.outbound_message_service import OutboundMessageService
from app.models import Contact, Conversation, Message, Tenant
from app.schemas import (
    AiModeUpdate,
    ContactListOut,
    ContactOut,
    ContactUpdate,
    ConversationListOut,
    ConversationOut,
    ConversationUpdate,
    MessageCreate,
    MessageListOut,
    MessageOut,
    MessagingAnalyticsOut,
    MessagingStatsOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/messaging", tags=["messaging"])

ConversationFilter = Literal[
    "all",
    "unread",
    "sms",
    "whatsapp",
    "ai_active",
    "human_mode",
    "closed",
]


@router.get("/health", response_model=MessagingHealthOut)
async def messaging_health() -> MessagingHealthOut:
    settings = get_settings()
    return MessagingHealthOut(
        status="ok",
        twilio_configured=settings.twilio_configured,
        sms_configured=settings.sms_configured,
        whatsapp_configured=settings.whatsapp_configured,
        openai_configured=settings.openai_configured,
    )


@router.get("/stats", response_model=MessagingStatsOut)
async def messaging_stats(
    auth: Annotated[AuthContext, Depends(get_current_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessagingStatsOut:
    base = select(Conversation).where(Conversation.tenant_id == auth.tenant_id)
    conversations = (await db.execute(base)).scalars().all()

    unread = 0
    for conversation in conversations:
        meta = conversation.metadata_json or {}
        if int(meta.get("unread_count") or 0) > 0:
            unread += 1

    return MessagingStatsOut(
        total_conversations=len(conversations),
        active_conversations=sum(1 for c in conversations if c.status == ConversationStatus.ACTIVE),
        unread_conversations=unread,
        ai_conversations=sum(1 for c in conversations if c.ai_enabled),
        human_mode_conversations=sum(1 for c in conversations if not c.ai_enabled),
        sms_conversations=sum(1 for c in conversations if c.channel == MessagingChannel.SMS),
        whatsapp_conversations=sum(
            1 for c in conversations if c.channel == MessagingChannel.WHATSAPP
        ),
        closed_conversations=sum(1 for c in conversations if c.status == ConversationStatus.CLOSED),
    )


@router.get("/analytics", response_model=MessagingAnalyticsOut)
async def messaging_analytics(
    auth: Annotated[AuthContext, Depends(get_current_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessagingAnalyticsOut:
    conversations = (
        await db.execute(select(Conversation).where(Conversation.tenant_id == auth.tenant_id))
    ).scalars().all()
    messages = (
        await db.execute(select(Message).where(Message.tenant_id == auth.tenant_id))
    ).scalars().all()

    by_channel: dict[str, int] = {}
    by_mode: dict[str, int] = {"ai": 0, "human": 0}
    by_status: dict[str, int] = {}
    for conversation in conversations:
        by_channel[conversation.channel.value] = by_channel.get(conversation.channel.value, 0) + 1
        by_status[conversation.status.value] = by_status.get(conversation.status.value, 0) + 1
        if conversation.ai_enabled:
            by_mode["ai"] += 1
        else:
            by_mode["human"] += 1

    by_day: dict[str, int] = {}
    delivery: dict[str, int] = {}
    failed = 0
    outbound = 0
    inbound = 0
    for message in messages:
        if message.created_at:
            key = message.created_at.date().isoformat()
            by_day[key] = by_day.get(key, 0) + 1
        if message.direction == MessageDirection.OUTBOUND:
            outbound += 1
            status = (message.provider_status or "unknown").lower()
            delivery[status] = delivery.get(status, 0) + 1
            if status in {"failed", "undelivered"}:
                failed += 1
        else:
            inbound += 1

    return MessagingAnalyticsOut(
        conversations_by_channel=[{"name": k, "value": v} for k, v in sorted(by_channel.items())],
        conversations_by_mode=[{"name": k, "value": v} for k, v in by_mode.items()],
        conversations_by_status=[{"name": k, "value": v} for k, v in sorted(by_status.items())],
        messages_by_day=[
            {"date": day, "count": by_day[day]} for day in sorted(by_day.keys())[-14:]
        ],
        delivery_status=[{"name": k, "value": v} for k, v in sorted(delivery.items())],
        total_messages=len(messages),
        outbound_messages=outbound,
        inbound_messages=inbound,
        failed_messages=failed,
    )


@router.get("/conversations", response_model=ConversationListOut)
async def list_conversations(
    auth: Annotated[AuthContext, Depends(get_current_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
    q: Annotated[str | None, Query()] = None,
    filter: Annotated[ConversationFilter, Query()] = "all",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ConversationListOut:
    stmt: Select[tuple[Conversation]] = (
        select(Conversation)
        .options(selectinload(Conversation.contact))
        .where(Conversation.tenant_id == auth.tenant_id)
    )

    if filter == "sms":
        stmt = stmt.where(Conversation.channel == MessagingChannel.SMS)
    elif filter == "whatsapp":
        stmt = stmt.where(Conversation.channel == MessagingChannel.WHATSAPP)
    elif filter == "ai_active":
        stmt = stmt.where(Conversation.ai_enabled.is_(True))
    elif filter == "human_mode":
        stmt = stmt.where(Conversation.ai_enabled.is_(False))
    elif filter == "closed":
        stmt = stmt.where(Conversation.status == ConversationStatus.CLOSED)
    elif filter == "unread":
        pass  # filtered in Python from metadata
    elif filter == "all":
        pass
    else:
        _assert_never(filter)

    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.join(Contact).where(
            or_(
                Contact.name.ilike(pattern),
                Contact.phone_number.ilike(pattern),
                Conversation.id.in_(
                    select(Message.conversation_id).where(
                        Message.tenant_id == auth.tenant_id,
                        Message.body.ilike(pattern),
                    )
                ),
            )
        )

    stmt = stmt.order_by(
        Conversation.last_message_at.desc().nullslast(),
        Conversation.created_at.desc(),
    )
    rows = (await db.execute(stmt)).scalars().unique().all()

    if filter == "unread":
        rows = [row for row in rows if int((row.metadata_json or {}).get("unread_count") or 0) > 0]

    total = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start : start + page_size]
    items = [await _conversation_out(db, row) for row in page_rows]
    return ConversationListOut(items=items, total=total, page=page, page_size=page_size)


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: UUID,
    auth: Annotated[AuthContext, Depends(get_current_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationOut:
    conversation = await _get_tenant_conversation(db, auth.tenant_id, conversation_id)
    return await _conversation_out(db, conversation)


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: UUID,
    payload: ConversationUpdate,
    auth: Annotated[AuthContext, Depends(get_current_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationOut:
    conversation = await _get_tenant_conversation(db, auth.tenant_id, conversation_id)
    if payload.status is not None:
        conversation.status = payload.status
    if payload.ai_enabled is not None:
        conversation.ai_enabled = payload.ai_enabled
    if payload.name is not None:
        contact = await db.get(Contact, conversation.contact_id)
        if contact is not None:
            contact.name = payload.name.strip() or None
    await db.flush()
    await db.refresh(conversation)
    return await _conversation_out(db, conversation)


@router.post("/conversations/{conversation_id}/ai-mode")
async def set_ai_mode(
    conversation_id: UUID,
    payload: AiModeUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(get_current_auth)],
) -> dict:
    """Toggle AI/human takeover for dashboard clients."""
    conversation = await _get_tenant_conversation(db, auth.tenant_id, conversation_id)
    conversation.ai_enabled = payload.ai_enabled
    await db.flush()
    return {
        "ok": True,
        "conversation_id": str(conversation.id),
        "ai_enabled": conversation.ai_enabled,
    }


@router.post("/conversations/{conversation_id}/ai-mode/form")
async def set_ai_mode_form(
    conversation_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(get_current_auth)],
    ai_enabled: Annotated[bool, Form()],
) -> dict:
    """Form-encoded AI mode toggle (curl / older clients)."""
    return await set_ai_mode(
        conversation_id,
        AiModeUpdate(ai_enabled=ai_enabled),
        db,
        auth,
    )


@router.get("/conversations/{conversation_id}/messages", response_model=MessageListOut)
async def list_messages(
    conversation_id: UUID,
    auth: Annotated[AuthContext, Depends(get_current_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before: Annotated[datetime | None, Query()] = None,
) -> MessageListOut:
    conversation = await _get_tenant_conversation(db, auth.tenant_id, conversation_id)

    stmt = select(Message).where(Message.conversation_id == conversation.id)
    if before is not None:
        stmt = stmt.where(Message.created_at < before)
    stmt = stmt.order_by(Message.created_at.desc()).limit(limit + 1)
    rows = list((await db.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    rows.reverse()

    # Opening the thread marks it read for the dashboard.
    meta = dict(conversation.metadata_json or {})
    if int(meta.get("unread_count") or 0) != 0:
        meta["unread_count"] = 0
        conversation.metadata_json = meta
        await db.flush()

    return MessageListOut(
        items=[MessageOut.model_validate(row) for row in rows],
        has_more=has_more,
        next_before=rows[0].created_at if has_more and rows else None,
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=201,
)
async def send_human_message(
    conversation_id: UUID,
    payload: MessageCreate,
    auth: Annotated[AuthContext, Depends(get_current_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageOut:
    conversation = await _get_tenant_conversation(db, auth.tenant_id, conversation_id)
    if conversation.status == ConversationStatus.CLOSED:
        raise HTTPException(status_code=400, detail="Conversation is closed")
    if conversation.status == ConversationStatus.ARCHIVED:
        raise HTTPException(status_code=400, detail="Conversation is archived")

    contact = await db.get(Contact, conversation.contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    settings = get_settings()
    provider = get_messaging_provider(settings)
    outbound = OutboundMessageService(db, settings=settings, provider=provider)
    status_callback_url = _status_callback_url(settings.twilio_webhook_base_url)

    try:
        message = await outbound.send_message(
            contact=contact,
            conversation=conversation,
            text=payload.body.strip(),
            channel=conversation.channel,
            role=MessageRole.HUMAN,
            status_callback_url=status_callback_url,
        )
    except TwilioSendError as exc:
        raise HTTPException(status_code=502, detail="Failed to send message") from exc

    return MessageOut.model_validate(message)


@router.get("/contacts", response_model=ContactListOut)
async def list_contacts(
    auth: Annotated[AuthContext, Depends(get_current_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
    q: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ContactListOut:
    stmt = select(Contact).where(Contact.tenant_id == auth.tenant_id)
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(Contact.name.ilike(pattern), Contact.phone_number.ilike(pattern)))
    stmt = stmt.order_by(Contact.updated_at.desc())
    rows = (await db.execute(stmt)).scalars().all()
    total = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start : start + page_size]
    items = [await _contact_out(db, auth.tenant_id, row) for row in page_rows]
    return ContactListOut(items=items, total=total, page=page, page_size=page_size)


@router.get("/contacts/{contact_id}", response_model=ContactOut)
async def get_contact(
    contact_id: UUID,
    auth: Annotated[AuthContext, Depends(get_current_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ContactOut:
    contact = await _get_tenant_contact(db, auth.tenant_id, contact_id)
    return await _contact_out(db, auth.tenant_id, contact)


@router.patch("/contacts/{contact_id}", response_model=ContactOut)
async def update_contact(
    contact_id: UUID,
    payload: ContactUpdate,
    auth: Annotated[AuthContext, Depends(get_current_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ContactOut:
    contact = await _get_tenant_contact(db, auth.tenant_id, contact_id)
    if payload.name is not None:
        contact.name = payload.name.strip() or None
    if payload.preferred_language is not None:
        contact.preferred_language = payload.preferred_language
    meta = dict(contact.metadata_json or {})
    if payload.notes is not None:
        meta["notes"] = payload.notes
    if payload.tags is not None:
        meta["tags"] = payload.tags
    contact.metadata_json = meta
    await db.flush()
    return await _contact_out(db, auth.tenant_id, contact)


@router.get("/contacts/{contact_id}/conversations", response_model=list[ConversationOut])
async def contact_conversations(
    contact_id: UUID,
    auth: Annotated[AuthContext, Depends(get_current_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ConversationOut]:
    await _get_tenant_contact(db, auth.tenant_id, contact_id)
    rows = (
        await db.execute(
            select(Conversation)
            .options(selectinload(Conversation.contact))
            .where(
                Conversation.tenant_id == auth.tenant_id,
                Conversation.contact_id == contact_id,
            )
            .order_by(Conversation.last_message_at.desc().nullslast())
        )
    ).scalars().all()
    return [await _conversation_out(db, row) for row in rows]


@router.post("/twilio/inbound")
async def twilio_inbound(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_twilio_signature: Annotated[str | None, Header(alias="X-Twilio-Signature")] = None,
) -> Response:
    """Twilio inbound webhook for both SMS and WhatsApp."""
    settings = get_settings()
    form = await request.form()
    params: dict[str, Any] = {key: form.get(key) for key in form.keys()}
    provider = get_messaging_provider(settings)

    webhook_url = _public_webhook_url(request, settings.twilio_webhook_base_url)
    if not provider.validate_webhook(url=webhook_url, params=params, signature=x_twilio_signature):
        logger.warning("Invalid Twilio signature on inbound webhook")
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    try:
        inbound = provider.normalize_inbound(params)
    except ValueError as exc:
        logger.warning("Invalid inbound Twilio payload: %s", exc)
        return Response(content="<Response></Response>", media_type="application/xml")

    tenant = await _default_tenant(db, settings.default_tenant_slug)
    status_callback_url = _status_callback_url(settings.twilio_webhook_base_url)

    service = InboundMessageService(db, settings=settings, provider=provider)
    try:
        await service.process_inbound(
            tenant_id=tenant.id,
            inbound=inbound,
            status_callback_url=status_callback_url,
        )
    except Exception:
        logger.exception(
            "Inbound processing failure provider=twilio channel=%s message_sid=%s",
            inbound.channel.value,
            inbound.message_id,
        )
        return Response(content="<Response></Response>", media_type="application/xml")

    return Response(content="<Response></Response>", media_type="application/xml")


@router.post("/twilio/status")
async def twilio_status(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_twilio_signature: Annotated[str | None, Header(alias="X-Twilio-Signature")] = None,
) -> dict:
    """Twilio delivery status callback."""
    settings = get_settings()
    form = await request.form()
    params: dict[str, Any] = {key: form.get(key) for key in form.keys()}
    provider = get_messaging_provider(settings)

    webhook_url = _public_webhook_url(request, settings.twilio_webhook_base_url)
    if not provider.validate_webhook(url=webhook_url, params=params, signature=x_twilio_signature):
        logger.warning("Invalid Twilio signature on status webhook")
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    try:
        status_update = provider.normalize_status(params)
    except ValueError as exc:
        logger.warning("Invalid Twilio status payload: %s", exc)
        return {"ok": False, "error": "invalid_payload"}

    outbound = OutboundMessageService(db, settings=settings, provider=provider)
    message = await outbound.update_provider_status(
        provider_message_sid=status_update.message_id,
        provider_status=status_update.status,
        metadata={
            "error_code": status_update.error_code,
            "channel": status_update.channel.value if status_update.channel else None,
        },
    )
    return {
        "ok": True,
        "updated": message is not None,
        "message_sid": status_update.message_id,
        "provider_status": status_update.status,
    }


async def _get_tenant_conversation(
    db: AsyncSession, tenant_id: UUID, conversation_id: UUID
) -> Conversation:
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.contact))
        .where(Conversation.id == conversation_id, Conversation.tenant_id == tenant_id)
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


async def _get_tenant_contact(db: AsyncSession, tenant_id: UUID, contact_id: UUID) -> Contact:
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.tenant_id == tenant_id)
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


async def _conversation_out(db: AsyncSession, conversation: Conversation) -> ConversationOut:
    contact = conversation.contact
    if contact is None:
        contact = await db.get(Contact, conversation.contact_id)

    latest = (
        await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    preview = None
    if latest is not None:
        preview = (latest.body or "").strip()
        if len(preview) > 120:
            preview = f"{preview[:117]}..."

    meta = conversation.metadata_json or {}
    return ConversationOut(
        id=conversation.id,
        contact_id=conversation.contact_id,
        channel=conversation.channel,
        status=conversation.status,
        ai_enabled=conversation.ai_enabled,
        assigned_user_id=conversation.assigned_user_id,
        last_message_at=conversation.last_message_at,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        contact_name=contact.name if contact else None,
        contact_phone=contact.phone_number if contact else None,
        preferred_language=contact.preferred_language if contact else None,
        latest_message_preview=preview,
        latest_message_at=latest.created_at if latest else conversation.last_message_at,
        unread_count=int(meta.get("unread_count") or 0),
        metadata={k: v for k, v in meta.items() if k not in {"raw"}},
    )


async def _contact_out(db: AsyncSession, tenant_id: UUID, contact: Contact) -> ContactOut:
    latest_conversation = (
        await db.execute(
            select(Conversation)
            .where(Conversation.tenant_id == tenant_id, Conversation.contact_id == contact.id)
            .order_by(Conversation.last_message_at.desc().nullslast())
            .limit(1)
        )
    ).scalar_one_or_none()

    open_conversation = (
        await db.execute(
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.contact_id == contact.id,
                Conversation.status == ConversationStatus.ACTIVE,
            )
            .order_by(Conversation.last_message_at.desc().nullslast())
            .limit(1)
        )
    ).scalar_one_or_none()

    meta = dict(contact.metadata_json or {})
    safe_meta = {k: v for k, v in meta.items() if k in {"notes", "tags", "lead_status"}}

    return ContactOut(
        id=contact.id,
        phone_number=contact.phone_number,
        name=contact.name,
        preferred_language=contact.preferred_language,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
        last_channel=latest_conversation.channel if latest_conversation else None,
        last_activity_at=(
            latest_conversation.last_message_at
            if latest_conversation and latest_conversation.last_message_at
            else contact.updated_at
        ),
        open_conversation_id=open_conversation.id if open_conversation else None,
        open_conversation_status=open_conversation.status if open_conversation else None,
        metadata=safe_meta,
    )


async def _default_tenant(db: AsyncSession, slug: str) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.slug == slug, Tenant.is_active.is_(True)))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=500, detail="Default tenant is not configured")
    return tenant


def _public_webhook_url(request: Request, configured_base: str) -> str:
    path = request.url.path
    query = f"?{request.url.query}" if request.url.query else ""
    if configured_base:
        return f"{configured_base.rstrip('/')}{path}{query}"
    return str(request.url)


def _status_callback_url(configured_base: str) -> str | None:
    if not configured_base:
        return None
    return f"{configured_base.rstrip('/')}/api/v1/messaging/twilio/status"


def _assert_never(value: ConversationFilter) -> None:
    raise HTTPException(status_code=400, detail=f"Unsupported filter: {value}")
