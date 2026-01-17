from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v2 import message
from app.auth.dependencies import get_current_user
from app.depends.db_depends import get_async_postgres_db
from app.models import Conversation as ConversationModel
from app.models import User as UserModel
from app.schemas.conversations import ConversationCreate, ConversationUpdate
from app.schemas.conversations import ConversationResponse as ConversationSchemas
from app.schemas.pagination import PaginatedResponse
from app.utils.utils_for_pagination import (
    calculate_has_more,
    decode_cursor,
    encode_cursor,
    trim_excess_item,
    validate_pagination_limit,
)


router = APIRouter(prefix="/conversations")

TAGS = "Conversations_V2"
DEFAULT_PER_PAGE = 20
MINIMUM_PER_PAGE = 1
MAXIMUM_PER_PAGE = 100


@router.get(
    "/",
    response_model=PaginatedResponse[ConversationSchemas],
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
    db: AsyncSession = Depends(get_async_postgres_db),
) -> PaginatedResponse[ConversationSchemas]:
    """
    Получить беседы пользователя с пагинацией (курсорной).

    **Пагинация:**
    - Использует курсорную пагинацию на основе created_at + id
    - Возвращает беседы от новых к старым
    - Поддерживает бесконечный скролл
    """
    logger.info(
        f"Запрос на получение бесед пользователя {current_user.id} "
        f"с пагинацией: limit={limit}, cursor={'да' if cursor else 'нет'}"
    )

    # Валидируем limit
    limit = validate_pagination_limit(limit, default=DEFAULT_PER_PAGE, maximum=MAXIMUM_PER_PAGE)

    # Формируем базовый запрос
    query = select(ConversationModel).where(ConversationModel.user_id == current_user.id)

    # Применяем курсор если указан
    if cursor:
        try:
            # Используем составной ключ (timestamp, id_uuid) для точного позиционирования
            timestamp, cursor_id_str = decode_cursor(cursor)
            id_uuid = UUID(cursor_id_str)

            query = query.where(
                (ConversationModel.created_at < timestamp)
                | ((ConversationModel.created_at == timestamp) & (ConversationModel.id < id_uuid))
            )
            logger.debug(f"Применён курсор: timestamp={timestamp}, id={id_uuid}")
        except ValueError as e:
            logger.warning(f"Невалидный курсор от пользователя {current_user.id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid cursor format: {str(e)}"
            ) from None

    # Используем составную сортировку для стабильности результатов
    query = query.order_by(ConversationModel.created_at.desc(), ConversationModel.id.desc())

    # Берём на один элемент больше для проверки has_next
    result = await db.scalars(query.limit(limit + 1))
    conversations = list(result.all())

    # Проверяем наличие следующей страницы
    has_next = calculate_has_more(conversations, limit)

    # Убираем лишний элемент если он есть
    conversations = trim_excess_item(conversations, limit, reverse=False)

    # Формируем курсор для следующей страницы
    next_cursor = None

    if conversations and has_next:
        last_conv = conversations[-1]
        next_cursor = encode_cursor(last_conv.created_at, last_conv.id)
        logger.debug(f"Сформирован курсор для следующей страницы на основе беседы {last_conv.id}")

    logger.info(
        f"Возвращено {len(conversations)} бесед, has_next={has_next}, next_cursor={'да' if next_cursor else 'нет'}"
    )

    return PaginatedResponse(
        items=conversations,
        next_cursor=next_cursor,
        has_next=has_next,
    )


@router.post(
    "/",
    response_model=ConversationSchemas,
    status_code=status.HTTP_201_CREATED,
    tags=[TAGS],
    summary="Создать новую беседу",
)
async def create_conversation(
    conversation_data: ConversationCreate,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> ConversationModel:
    """
    Создать новую беседу для текущего пользователя.
    """
    logger.info(f"Запрос на создание беседы пользователем {current_user.id}")

    conversation = ConversationModel(user_id=current_user.id, title=conversation_data.title or "New conversation")
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)

    logger.info(f"Создана беседа {conversation.id} для пользователя {current_user.id}")

    return cast(ConversationModel, conversation)


@router.patch(
    "/{conversation_id}",
    response_model=ConversationSchemas,
    status_code=status.HTTP_200_OK,
    tags=[TAGS],
    summary="Обновить беседу",
)
async def update_conversation(
    conversation_id: UUID,
    conversation_data: ConversationUpdate,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> ConversationModel:
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

    return cast(ConversationModel, conversation)


@router.delete("/{conversation_id}", status_code=status.HTTP_200_OK, tags=[TAGS], summary="Удалить беседу")
async def delete_conversation(
    conversation_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> dict[str, str]:
    """
    Полное удаление беседы по UUID из БД (включая все сообщения).

    **Внимание:** Это действие необратимо!
    """
    logger.info(f"Запрос на удаление беседы {conversation_id} пользователем {current_user.id}")

    conversation = await db.get(ConversationModel, conversation_id)

    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    await db.delete(conversation)
    await db.commit()

    logger.info(f"Удалена беседа {conversation_id}")

    return {"message": "Conversation deleted"}


router.include_router(message.router)
