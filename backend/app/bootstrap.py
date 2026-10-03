from sqlalchemy import select

from app.auth import hash_password
from app.config import get_settings
from app.db.base import Base
from app.db.session import AsyncSessionLocal, engine
from app.models import (  # noqa: F401 — register metadata
    Contact,
    Conversation,
    Message,
    Tenant,
    User,
    UserRole,
)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_default_tenant()
    await ensure_bootstrap_admin()


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


async def ensure_bootstrap_admin() -> None:
    """Create a default dashboard user when none exists for the tenant."""
    settings = get_settings()
    if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
        return

    async with AsyncSessionLocal() as db:
        tenant_result = await db.execute(
            select(Tenant).where(Tenant.slug == settings.default_tenant_slug)
        )
        tenant = tenant_result.scalar_one_or_none()
        if tenant is None:
            return

        existing = await db.execute(
            select(User).where(
                User.tenant_id == tenant.id,
                User.email == settings.bootstrap_admin_email.lower(),
            )
        )
        if existing.scalar_one_or_none() is not None:
            return

        db.add(
            User(
                tenant_id=tenant.id,
                email=settings.bootstrap_admin_email.lower(),
                full_name=settings.bootstrap_admin_name,
                hashed_password=hash_password(settings.bootstrap_admin_password),
                role=UserRole.OWNER,
                is_active=True,
            )
        )
        await db.commit()
