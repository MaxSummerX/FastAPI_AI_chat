from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger

from app.application.exceptions.conversation import ConversationNotFoundError
from app.application.schemas.conversation import ConversationCreate, ConversationResponse, ConversationUpdate
from app.application.schemas.pagination import PaginatedResponse
from app.application.services.conversation_service import ConversationService
from app.domain.models.user import User as UserModel
from app.infrastructure.persistence.pagination import (
    DEFAULT_PER_PAGE,
    MINIMUM_PER_PAGE,
    InvalidCursorError,
)
from app.presentation.dependencies import get_conversation_service, get_current_user
from app.presentation.routers.v2 import message


router = APIRouter(prefix="/conversations")

TAGS = "Conversations"


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    tags=[TAGS],
    summary="Получить беседы пользователя с пагинацией",
)
async def get_conversations(
    limit: int = Query(
        default=DEFAULT_PER_PAGE, ge=MINIMUM_PER_PAGE, description="Размер страницы (1-100). По умолчанию: 20"
    ),
    cursor: str | None = Query(
        default=None, description="Курсор для следующей страницы. Берётся из предыдущего ответа"
    ),
    current_user: UserModel = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> PaginatedResponse[ConversationResponse]:
    """
    Возвращает беседы текущего пользователя с курсорной пагинацией.

    **Возможные ошибки:**
    - `400` — невалидный формат курсора
    """
    try:
        return await service.get_user_conversations(
            limit=limit,
            cursor=cursor,
            user_id=current_user.id,
        )
    except InvalidCursorError as e:
        logger.warning("Невалидный курсор пользователя {}: {}", current_user.id, str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    tags=[TAGS],
    summary="Создать новую беседу",
)
async def create_conversation(
    conversation_data: ConversationCreate,
    current_user: UserModel = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationResponse:
    """
    Создаёт новую беседу для текущего пользователя.

    **Возможные ошибки:**
    - `422` — некорректные данные беседы
    """
    try:
        return await service.create_conversation(conversation_data=conversation_data, user_id=current_user.id)

    except Exception as e:
        logger.error("Ошибка при создании беседы пользователем {}: {}", current_user.id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating conversation"
        ) from None


@router.patch(
    "/{conversation_id}",
    status_code=status.HTTP_200_OK,
    tags=[TAGS],
    summary="Обновить беседу",
)
async def update_conversation(
    conversation_id: UUID,
    conversation_data: ConversationUpdate,
    current_user: UserModel = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationResponse:
    """
    Обновляет беседу пользователя.

    Выполняет частичное обновление — обновляются только переданные поля.

    **Возможные ошибки:**
    - `404` — беседа не найдена или принадлежит другому пользователю
    """
    try:
        return await service.update_conversation(
            conversation_id=conversation_id, conversation_data=conversation_data, user_id=current_user.id
        )

    except ConversationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None

    except Exception as e:
        logger.error("Ошибка при обновлении беседы: {} пользователем {}: {}", conversation_id, current_user.id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating conversation"
        ) from None


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, tags=[TAGS], summary="Удалить беседу")
async def delete_conversation(
    conversation_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    service: ConversationService = Depends(get_conversation_service),
) -> None:
    """
    Удаляет беседу пользователя.

    Выполняет полное удаление беседы из базы данных.

    **Возможные ошибки:**
    - `404` — беседа не найдена или принадлежит другому пользователю
    """
    try:
        await service.delete_conversation(conversation_id=conversation_id, user_id=current_user.id)

    except ConversationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None

    except Exception as e:
        logger.error("Ошибка при удалении беседы: {} пользователем {}: {}", conversation_id, current_user.id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting conversation"
        ) from None


router.include_router(message.router)
