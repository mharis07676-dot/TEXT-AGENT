from sqlalchemy import select

from app.config import get_settings
from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.models import (  # noqa: F401 — register metadata
    Contact,
    Conversation,
    Message,
    Tenant,
    User,
)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_default_tenant()


async def ensure_default_tenant() -> None:
    settings = get_settings()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Tenant).where(Tenant.slug == settings.default_tenant_slug))
        tenant = result.scalar_one_or_none()
        if tenant is None:
            db.add(
                Tenant(
                    name="Synas",
                    slug=settings.default_tenant_slug,
                    is_active=True,
                    settings={},
                )
            )
            await db.commit()
