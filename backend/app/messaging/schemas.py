from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.messaging.enums import MessagingChannel, MessagingProviderName


class NormalizedInboundMessage(BaseModel):
    provider: MessagingProviderName
    channel: MessagingChannel
    message_id: str
    from_number: str
    to_number: str
    text: str = ""
    media_urls: list[str] = Field(default_factory=list)
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedStatusUpdate(BaseModel):
    provider: MessagingProviderName
    message_id: str
    status: str
    channel: MessagingChannel | None = None
    error_code: str | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class MessagingHealthOut(BaseModel):
    status: str
    twilio_configured: bool
    sms_configured: bool
    whatsapp_configured: bool
    openai_configured: bool


class OutboundSendResult(BaseModel):
    provider_message_sid: str
    provider_status: str | None = None
    channel: MessagingChannel


class ConversationHistoryItem(BaseModel):
    role: str
    body: str
    channel: str
    direction: str
    created_at: str | None = None


class TextAgentContext(BaseModel):
    contact_id: UUID
    contact_name: str | None = None
    phone_number: str
    preferred_language: str
    conversation_id: UUID
    channel: MessagingChannel
    history: list[ConversationHistoryItem] = Field(default_factory=list)
    latest_user_message: str
    known_facts: dict[str, str] = Field(default_factory=dict)
    is_new_conversation: bool = False
