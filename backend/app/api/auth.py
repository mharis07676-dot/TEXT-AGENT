from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthContext, create_access_token, get_current_auth, hash_password, verify_password
from app.db.session import get_db
from app.models import Tenant, User
from app.schemas import LoginRequest, TokenOut, UserCreate, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
async def login(
    payload: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenOut:
    tenant_result = await db.execute(select(Tenant).where(Tenant.slug == payload.tenant_slug))
    tenant = tenant_result.scalar_one_or_none()
    if tenant is None or not tenant.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    user_result = await db.execute(
        select(User).where(
            User.tenant_id == tenant.id,
            User.email == payload.email.lower(),
            User.is_active.is_(True),
        )
    )
    user = user_result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        email=user.email,
    )
    return TokenOut(access_token=token)


@router.get("/me", response_model=UserOut)
async def me(
    auth: Annotated[AuthContext, Depends(get_current_auth)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    result = await db.execute(
        select(User).where(User.id == auth.user_id, User.tenant_id == auth.tenant_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post("/tenants/{tenant_id}/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    tenant_id: UUID,
    payload: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(get_current_auth)],
) -> User:
    if auth.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")
    tenant = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    if tenant.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    existing = await db.execute(
        select(User).where(User.tenant_id == tenant_id, User.email == payload.email.lower())
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")

    user = User(
        tenant_id=tenant_id,
        email=payload.email.lower(),
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    await db.flush()
    return user
