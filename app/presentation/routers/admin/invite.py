from fastapi import APIRouter, Depends, Query, status

from app.application.schemas.invite import (
    InviteDeleteResponse,
    InviteListResponse,
)
from app.application.services.invite_service import InviteService
from app.domain.models.user import User as UserModel
from app.presentation.dependencies import get_current_admin_user, get_invite_service


router = APIRouter(prefix="/invites")


@router.post("", status_code=status.HTTP_201_CREATED, summary="Сгенерировать инвайт-коды")
async def generate_invite_codes(
    count: int = Query(1, ge=1, le=10, description="Количество кодов для генерации (1-10)"),
    current_admin: UserModel = Depends(get_current_admin_user),
    invite_service: InviteService = Depends(get_invite_service),
) -> InviteListResponse:
    """Генерирует указанное количество уникальных инвайт-кодов для регистрации новых пользователей."""
    return await invite_service.generate_invite_codes(count, current_admin.id)


@router.get("/unused", status_code=status.HTTP_200_OK, summary="Получить неиспользованные инвайт-коды")
async def get_all_unused_codes(
    skip: int = 0,
    limit: int = 10,
    current_admin: UserModel = Depends(get_current_admin_user),
    invite_service: InviteService = Depends(get_invite_service),
) -> InviteListResponse:
    """Возвращает список неиспользованных инвайт-кодов с пагинацией."""
    return await invite_service.unused_codes(skip, limit, current_admin.id)


@router.delete(
    "/unused",
    status_code=status.HTTP_200_OK,
    summary="Удалить все неиспользованные инвайт-коды",
)
async def delete_all_unused_invites(
    current_admin: UserModel = Depends(get_current_admin_user),
    invite_service: InviteService = Depends(get_invite_service),
) -> InviteDeleteResponse:
    """Удаляет все неиспользованные инвайт-коды."""
    return await invite_service.delete_all_unused(current_admin.id)
