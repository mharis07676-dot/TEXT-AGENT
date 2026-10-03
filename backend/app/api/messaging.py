from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.messaging.dispatcher import get_messaging_provider
from app.messaging.schemas import MessagingHealthOut
from app.messaging.services.inbound_message_service import InboundMessageService
from app.messaging.services.outbound_message_service import OutboundMessageService
from app.models import Tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/messaging", tags=["messaging"])


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
        # Acknowledge with empty TwiML so Twilio does not retry forever on bad payloads.
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
        # Still return 200/TwiML so Twilio retries are controlled; details stay in logs.
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


@router.post("/conversations/{conversation_id}/ai-mode")
async def set_ai_mode(
    conversation_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    ai_enabled: Annotated[bool, Form()],
) -> dict:
    """Lightweight control for AI/human takeover (dashboard can call later)."""
    from app.models import Conversation

    result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conversation.ai_enabled = ai_enabled
    await db.flush()
    return {
        "ok": True,
        "conversation_id": str(conversation.id),
        "ai_enabled": conversation.ai_enabled,
    }


async def _default_tenant(db: AsyncSession, slug: str) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.slug == slug, Tenant.is_active.is_(True)))
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=500, detail="Default tenant is not configured")
    return tenant


def _public_webhook_url(request: Request, configured_base: str) -> str:
    """Prefer configured public HTTPS base (Railway) over internal request URL."""
    path = request.url.path
    query = f"?{request.url.query}" if request.url.query else ""
    if configured_base:
        return f"{configured_base.rstrip('/')}{path}{query}"
    # Fallback for local/dev; Twilio signature validation may fail without public URL.
    return str(request.url)


def _status_callback_url(configured_base: str) -> str | None:
    if not configured_base:
        return None
    return f"{configured_base.rstrip('/')}/api/v1/messaging/twilio/status"
