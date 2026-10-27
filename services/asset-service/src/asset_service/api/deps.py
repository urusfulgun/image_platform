"""FastAPI dependency injection helpers."""

import uuid
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from asset_service.db.session import get_db
from asset_service.db.models import UserModel
from sqlalchemy import select


async def get_current_user_id(request: Request) -> uuid.UUID:
    """Extract the authenticated user's KeyCloak sub from the DPoP token claims.

    The BFF attaches X-User-Sub header after validating the DPoP-bound token.
    In production, verify the JWT signature here; for dev, trust the header.
    """
    user_sub = request.headers.get("X-User-Sub")
    if not user_sub:
        raise HTTPException(status_code=401, detail="Missing user identity")
    try:
        return uuid.UUID(user_sub)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid user identity format")


async def get_local_user(
    kc_sub: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> UserModel:
    """Resolve the shadow user from the local DB by KeyCloak sub."""
    result = await db.execute(select(UserModel).where(UserModel.kc_sub == kc_sub))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not synced yet")
    return user
