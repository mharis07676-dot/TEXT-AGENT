import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base

# JSONB on Postgres; JSON elsewhere (tests / sqlite).
JSONType = JSON().with_variant(JSONB(), "postgresql")


def _enum_column(enum_cls: type[enum.Enum], **kwargs):
    """Store enum values as strings for Postgres + SQLite test compatibility."""
    return Enum(enum_cls, values_callable=lambda obj: [item.value for item in obj], **kwargs)


class UserRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    AGENT = "agent"
    VIEWER = "viewer"


class MessagingChannel(str, enum.Enum):
    SMS = "sms"
    WHATSAPP = "whatsapp"


class ConversationStatus(str, enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    ARCHIVED = "archived"


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    HUMAN = "human"
    SYSTEM = "system"


class MessageDirection(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessagingProviderName(str, enum.Enum):
    TWILIO = "twilio"


class PreferredLanguage(str, enum.Enum):
    ENGLISH = "english"
    ROMAN_URDU = "roman_urdu"
    URDU = "urdu"
    UNKNOWN = "unknown"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    settings: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    users: Mapped[list["User"]] = relationship(back_populates="tenant")
    contacts: Mapped[list["Contact"]] = relationship(back_populates="tenant")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="tenant")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(_enum_column(UserRole), default=UserRole.AGENT)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tenant: Mapped[Tenant] = relationship(back_populates="users")


class Contact(Base):
    """Text-channel contact. Compatible in spirit with voice-agent Customer."""

    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "phone_number", name="uq_contacts_tenant_phone"),
        Index("ix_contacts_phone_number", "phone_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    preferred_language: Mapped[PreferredLanguage] = mapped_column(
        _enum_column(PreferredLanguage), default=PreferredLanguage.UNKNOWN
    )
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tenant: Mapped[Tenant] = relationship(back_populates="contacts")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="contact")


class Conversation(Base):
    """Shared SMS/WhatsApp conversation thread (not voice-call-bound)."""

    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_contact_id", "contact_id"),
        Index("ix_conversations_status", "status"),
        Index("ix_conversations_last_message_at", "last_message_at"),
        Index(
            "ix_conversations_active_lookup",
            "tenant_id",
            "contact_id",
            "channel",
            "status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contacts.id"), nullable=False)
    channel: Mapped[MessagingChannel] = mapped_column(_enum_column(MessagingChannel), nullable=False)
    status: Mapped[ConversationStatus] = mapped_column(
        _enum_column(ConversationStatus), default=ConversationStatus.ACTIVE, nullable=False
    )
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tenant: Mapped[Tenant] = relationship(back_populates="conversations")
    contact: Mapped[Contact] = relationship(back_populates="conversations")
    assigned_user: Mapped[User | None] = relationship()
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("provider", "provider_message_sid", name="uq_messages_provider_sid"),
        Index("ix_messages_conversation_id", "conversation_id"),
        Index("ix_messages_created_at", "created_at"),
        Index("ix_messages_provider_message_sid", "provider_message_sid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    role: Mapped[MessageRole] = mapped_column(_enum_column(MessageRole), nullable=False)
    direction: Mapped[MessageDirection] = mapped_column(_enum_column(MessageDirection), nullable=False)
    channel: Mapped[MessagingChannel] = mapped_column(_enum_column(MessagingChannel), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    provider: Mapped[MessagingProviderName] = mapped_column(
        _enum_column(MessagingProviderName), default=MessagingProviderName.TWILIO, nullable=False
    )
    provider_message_sid: Mapped[str | None] = mapped_column(String(128))
    provider_status: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
