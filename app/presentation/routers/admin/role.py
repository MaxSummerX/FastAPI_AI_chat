from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger

from app.application.exceptions.user import UserAlreadyAdminException, UserNotFoundException
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
    - `400` — пользователь уже является администратором
    - `404` — пользователь не найден
    """
    try:
        return await service.promote_to_admin(user_id)

    except UserNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None

    except UserAlreadyAdminException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None

    except Exception as e:
        logger.error("Ошибка при попытка повысить пользователя {}: {}", user_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving user information",
        ) from None
