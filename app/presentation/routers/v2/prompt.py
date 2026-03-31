from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger

from app.application.exceptions.prompt import PromptNotFoundError
from app.application.schemas.pagination import PaginatedResponse
from app.application.schemas.prompt import PromptCreate, PromptResponse, PromptUpdate
from app.application.services.prompt_service import PromptService
from app.domain.models.user import User as UserModel
from app.infrastructure.persistence.pagination import (
    DEFAULT_PER_PAGE,
    MINIMUM_PER_PAGE,
    InvalidCursorError,
)
from app.presentation.dependencies import get_current_user, get_prompt_service


router = APIRouter(prefix="/prompts", tags=["Prompts"])


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Получить промпты пользователя с пагинацией",
)
async def get_user_prompts(
    limit: int = Query(
        default=DEFAULT_PER_PAGE, ge=MINIMUM_PER_PAGE, description="Размер страницы (1-100). По умолчанию: 20"
    ),
    cursor: str | None = Query(
        default=None, description="Курсор для следующей страницы. Берётся из предыдущего ответа"
    ),
    include_inactive: bool = Query(default=False, description="Включать неактивные промпты в результаты"),
    current_user: UserModel = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
) -> PaginatedResponse[PromptResponse]:
    """
    Возвращает промпты текущего пользователя с курсорной пагинацией.

    **Возможные ошибки:**
    - `400` — невалидный формат курсора
    """
    try:
        return await service.get_user_prompts(
            limit=limit,
            cursor=cursor,
            user_id=current_user.id,
            include_inactive=include_inactive,
        )
    except InvalidCursorError as e:
        logger.warning("Невалидный курсор пользователя {}: {}", current_user.id, str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


@router.get(
    "/{prompt_id}",
    status_code=status.HTTP_200_OK,
    summary="Получить промпт по ID",
)
async def get_prompt(
    prompt_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
) -> PromptResponse:
    """
    Возвращает промпт по его ID.

    **Возможные ошибки:**
    - `404` — промпт не найден или принадлежит другому пользователю
    """
    try:
        return await service.get_user_prompt(prompt_id=prompt_id, user_id=current_user.id)
    except PromptNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except Exception as e:
        logger.error("Ошибка при получении промпта {} пользователем {}: {}", prompt_id, current_user.id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving prompt"
        ) from None


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Создать новый промпт",
)
async def create_prompt(
    prompt_data: PromptCreate,
    current_user: UserModel = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
) -> PromptResponse:
    """
    Создаёт новый промпт для текущего пользователя.

    **Возможные ошибки:**
    - `422` — некорректные данные промпта
    """
    try:
        return await service.create_prompt(prompt_data=prompt_data, user_id=current_user.id)
    except Exception as e:
        logger.error("Ошибка при создании промпта пользователем {}: {}", current_user.id, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating prompt") from None


@router.patch(
    "/{prompt_id}",
    status_code=status.HTTP_200_OK,
    summary="Обновить промпт",
)
async def update_prompt(
    prompt_id: UUID,
    prompt_data: PromptUpdate,
    current_user: UserModel = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
) -> PromptResponse:
    """
    Обновляет промпт пользователя.

    Выполняет частичное обновление — обновляются только переданные поля.

    **Возможные ошибки:**
    - `404` — промпт не найден или принадлежит другому пользователю
    """
    try:
        return await service.update_prompt(prompt_id=prompt_id, prompt_data=prompt_data, user_id=current_user.id)
    except PromptNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except Exception as e:
        logger.error("Ошибка при обновлении промпта {} пользователем {}: {}", prompt_id, current_user.id, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating prompt") from None


@router.delete(
    "/{prompt_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить промпт",
)
async def delete_prompt(
    prompt_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    service: PromptService = Depends(get_prompt_service),
) -> None:
    """
    Удаляет промпт пользователя (мягкое удаление).

    Промпт помечается как неактивный, но остаётся в базе данных.

    **Возможные ошибки:**
    - `404` — промпт не найден или принадлежит другому пользователю
    """
    try:
        await service.soft_delete_user_prompt(prompt_id=prompt_id, user_id=current_user.id)
    except PromptNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
    except Exception as e:
        logger.error("Ошибка при удаление промпта: {} пользователем {}: {}", prompt_id, current_user.id, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting prompt") from None
