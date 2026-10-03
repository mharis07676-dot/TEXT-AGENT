from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models import (
    ConversationStatus,
    MessageDirection,
    MessageRole,
    MessagingChannel,
    PreferredLanguage,
    UserRole,
)


class LoginRequest(BaseModel):
    email: str
    password: str
    tenant_slug: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: str
    full_name: str
    password: str = Field(min_length=8)
    role: UserRole = UserRole.AGENT


class UserOut(BaseModel):
    id: UUID
    tenant_id: UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ContactOut(BaseModel):
    id: UUID
    phone_number: str
    name: str | None = None
    preferred_language: PreferredLanguage
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_channel: MessagingChannel | None = None
    last_activity_at: datetime | None = None
    open_conversation_id: UUID | None = None
    open_conversation_status: ConversationStatus | None = None
    metadata: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class ContactUpdate(BaseModel):
    name: str | None = None
    preferred_language: PreferredLanguage | None = None
    notes: str | None = None
    tags: list[str] | None = None


class ConversationOut(BaseModel):
    id: UUID
    contact_id: UUID
    channel: MessagingChannel
    status: ConversationStatus
    ai_enabled: bool
    assigned_user_id: UUID | None = None
    last_message_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    preferred_language: PreferredLanguage | None = None
    latest_message_preview: str | None = None
    latest_message_at: datetime | None = None
    unread_count: int = 0
    metadata: dict = Field(default_factory=dict)


class ConversationUpdate(BaseModel):
    status: ConversationStatus | None = None
    ai_enabled: bool | None = None
    name: str | None = None


class AiModeUpdate(BaseModel):
    ai_enabled: bool


class MessageOut(BaseModel):
    id: UUID
    conversation_id: UUID
    role: MessageRole
    direction: MessageDirection
    channel: MessagingChannel
    body: str
    provider_status: str | None = None
    provider_message_sid: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class MessageListOut(BaseModel):
    items: list[MessageOut]
    has_more: bool = False
    next_before: datetime | None = None


class ConversationListOut(BaseModel):
    items: list[ConversationOut]
    total: int
    page: int
    page_size: int


class ContactListOut(BaseModel):
    items: list[ContactOut]
    total: int
    page: int
    page_size: int


class MessagingStatsOut(BaseModel):
    total_conversations: int
    active_conversations: int
    unread_conversations: int
    ai_conversations: int
    human_mode_conversations: int
    sms_conversations: int
    whatsapp_conversations: int
    closed_conversations: int


class MessagingAnalyticsOut(BaseModel):
    conversations_by_channel: list[dict]
    conversations_by_mode: list[dict]
    conversations_by_status: list[dict]
    messages_by_day: list[dict]
    delivery_status: list[dict]
    total_messages: int
    outbound_messages: int
    inbound_messages: int
    failed_messages: int
