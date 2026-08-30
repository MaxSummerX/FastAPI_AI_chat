from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.application.schemas.user import UserResponseBase
from app.application.services.user_service import UserService
from app.domain.models.user import User as UserModel
from app.presentation.dependencies import get_current_admin_user, get_user_service


router = APIRouter(prefix="/role")


@router.patch("/{user_id}", status_code=status.HTTP_200_OK, summary="Повысить пользователя до администратора")
async def promote_to_admin(
    user_id: UUID,
    current_admin: UserModel = Depends(get_current_admin_user),
    service: UserService = Depends(get_user_service),
) -> UserResponseBase:
    """
    Повышает указанного пользователя до роли администратора.

    **Возможные ошибки:**
    - `409` — пользователь уже является администратором
    - `404` — пользователь не найден
    """
    return await service.promote_to_admin(user_id)
