"""Initial text messaging schema.

Revision ID: 20261004_0001
Revises:
Create Date: 2026-10-04

Uses SQLAlchemy metadata create_all for the text-agent models.
Prefer backend/migrations/001_text_messaging.sql for explicit SQL applies.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from app.db.base import Base
from app.models import Contact, Conversation, Message, Tenant, User  # noqa: F401

revision: str = "20261004_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
