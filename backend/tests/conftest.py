from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Generator
from uuid import uuid4

# Must run before app imports that construct the SQLAlchemy engine.
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_URL_SYNC", "sqlite:///:memory:")
os.environ.setdefault("DEBUG", "false")

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.base import Base
from app.models import Tenant

get_settings.cache_clear()


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        tenant = Tenant(id=uuid4(), name="Synas", slug="synas", is_active=True, settings={})
        session.add(tenant)
        await session.commit()
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def tenant_id(db_session: AsyncSession):
    from sqlalchemy import select

    result = await db_session.execute(select(Tenant).where(Tenant.slug == "synas"))
    tenant = result.scalar_one()
    return tenant.id
