from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.conversation import ConversationCreate, ConversationUpdate
from app.application.schemas.conversation import ConversationResponse as ConversationSchemas
from app.application.schemas.pagination import PaginatedResponse
from app.domain.models.conversation import Conversation as ConversationModel
from app.domain.models.user import User as UserModel
from app.infrastructure.database.dependencies import get_db
from app.infrastructure.persistence.pagination import (
    DEFAULT_PER_PAGE,
    MINIMUM_PER_PAGE,
    InvalidCursorError,
    paginate_with_cursor,
)
from app.presentation.dependencies import get_current_user
from app.presentation.routers.v2 import message


router = APIRouter(prefix="/conversations")

TAGS = "Conversations_V2"


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
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[ConversationSchemas]:
    """
    Получить беседы пользователя с пагинацией (курсорной).
    """
    logger.info(
        f"Запрос на получение бесед пользователя {current_user.id} "
        f"с пагинацией: limit={limit}, cursor={'да' if cursor else 'нет'}"
    )

    # Формируем базовый запрос
    query = select(ConversationModel).where(ConversationModel.user_id == current_user.id)

    try:
        conversations, next_cursor, has_next = await paginate_with_cursor(
            db=db,
            query=query,
            cursor=cursor,
            limit=limit,
            model=ConversationModel,
        )
    except InvalidCursorError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None

    logger.info(
        f"Возвращено {len(conversations)} бесед, has_next={has_next}, next_cursor={'да' if next_cursor else 'нет'}"
    )

    return PaginatedResponse(
        items=[ConversationSchemas.model_validate(conversation) for conversation in conversations],
        next_cursor=next_cursor,
        has_next=has_next,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    tags=[TAGS],
    summary="Создать новую беседу",
)
async def create_conversation(
    conversation_data: ConversationCreate,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationSchemas:
    """
    Создать новую беседу для текущего пользователя.
    """
    logger.info(f"Запрос на создание беседы пользователем {current_user.id}")

    conversation = ConversationModel(user_id=current_user.id, title=conversation_data.title or "New conversation")
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)

    logger.info(f"Создана беседа {conversation.id} для пользователя {current_user.id}")

    return ConversationSchemas.model_validate(conversation)


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
    db: AsyncSession = Depends(get_db),
) -> ConversationSchemas:
    """
    Переименовать беседу или отправить её в архив.
    """
    logger.info(f"Запрос на обновление беседы {conversation_id} пользователя {current_user.id}")

    result = await db.execute(
        update(ConversationModel)
        .where(ConversationModel.id == conversation_id, ConversationModel.user_id == current_user.id)
        .values(**conversation_data.model_dump(exclude_unset=True, by_alias=False))
        .returning(ConversationModel)
    )

    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    await db.commit()
    await db.refresh(conversation)

    logger.info(f"Обновлена беседа {conversation.id} для пользователя {current_user.id}")

    return ConversationSchemas.model_validate(conversation)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, tags=[TAGS], summary="Удалить беседу")
async def delete_conversation(
    conversation_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Полное удаление беседы по UUID из БД (включая все сообщения).

    **Внимание:** Это действие необратимо!
    """
    logger.info(f"Запрос на удаление беседы {conversation_id} пользователем {current_user.id}")

    result = await db.scalars(
        select(ConversationModel).where(
            ConversationModel.id == conversation_id, ConversationModel.user_id == current_user.id
        )
    )
    conversation = result.first()

    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    await db.delete(conversation)
    await db.commit()

    logger.info(f"Удалена беседа {conversation_id}")


router.include_router(message.router)
