from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_admin_user
from app.depends.db_depends import get_async_postgres_db
from app.enum.roles import UserRole
from app.models.users import User as UserModel
from app.schemas.users import UserResponseFull


router = APIRouter(prefix="/role", tags=["Role"])


@router.patch("/{user_id}", status_code=status.HTTP_200_OK, summary="")
async def promote_to_admin(
    user_id: UUID,
    admin: UserModel = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> UserResponseFull:
    result = await db.execute(
        select(UserModel).where(
            UserModel.id == user_id,
            UserModel.is_active.is_(True),
            UserModel.is_verified.is_(True),
        )
    )

    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found or not verified")

    if user.role == UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already an admin")

    user.role = UserRole.ADMIN
    await db.commit()
    await db.refresh(user)
    return UserResponseFull.model_validate(user)
