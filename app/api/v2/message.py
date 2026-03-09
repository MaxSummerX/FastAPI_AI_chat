from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.configs.llm_config import base_config_for_llm
from app.depends.db_depends import get_async_postgres_db
from app.exceptions.exceptions import LLMGenerationError, NotFoundError, ValidationError  # TODO: настроить исключения
from app.llms.openai import AsyncOpenAILLM
from app.models import Conversation as ConversationModel
from app.models import Message as MessageModel
from app.models import User as UserModel
from app.schemas.messages import MessageResponse as MessageSchemas
from app.schemas.messages import MessageStreamRequest
from app.schemas.pagination import PaginatedResponse
from app.services.message_service import MessageService, get_message_service
from app.utils.utils_for_pagination import (
    calculate_has_more,
    decode_cursor,
    encode_cursor,
    trim_excess_item,
    validate_pagination_limit,
)


router = APIRouter(prefix="/{conversation_id}/messages", tags=["Messages_v2"])


llm = AsyncOpenAILLM(base_config_for_llm)

DEFAULT_PER_PAGE = 20
MINIMUM_PER_PAGE = 1
MAXIMUM_PER_PAGE = 100


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Получить сообщения c пагинацией",
)
async def get_messages(
    conversation_id: UUID,
    limit: int = Query(
        default=DEFAULT_PER_PAGE, ge=MINIMUM_PER_PAGE, description="Размер страницы (1-100). По умолчанию: 20"
    ),
    cursor: str | None = Query(
        default=None, description="Курсор для загрузки более старых сообщений. Берётся из предыдущего ответа"
    ),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> PaginatedResponse[MessageSchemas]:
    """
    Получить историю сообщений с курсорной пагинацией.
    """
    logger.info(f"Запрос сообщений беседы {conversation_id} от пользователя {current_user.id}")

    # Валидация limit
    limit = validate_pagination_limit(limit=limit, default=DEFAULT_PER_PAGE, maximum=MAXIMUM_PER_PAGE)

    # Проверка существования беседы и прав доступа
    conversation_result = await db.scalars(
        select(ConversationModel).where(
            ConversationModel.id == conversation_id, ConversationModel.user_id == current_user.id
        )
    )
    conversation = conversation_result.first()

    if not conversation:
        logger.warning(f"Попытка доступа к несуществующей беседе {conversation_id} пользователем {current_user.id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # Формируем базовый запрос
    query = select(MessageModel).where(MessageModel.conversation_id == conversation_id)

    # Применяем курсор если указан
    if cursor:
        # Используем составной ключ (timestamp, id_uuid) для точного позиционирования
        try:
            timestamp, cursor_id_str = decode_cursor(cursor)
            id_uuid = UUID(cursor_id_str)

            query = query.where(
                (MessageModel.timestamp < timestamp)
                | ((MessageModel.timestamp == timestamp) & (MessageModel.id < id_uuid))
            )
            logger.debug(f"Применён курсор: timestamp={timestamp}, id={id_uuid}")
        except ValueError as e:
            logger.warning(f"Невалидный курсор от пользователя {current_user.id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid cursor format: {str(e)}"
            ) from None

    # Используем составную сортировку для стабильности результатов
    query = query.order_by(MessageModel.timestamp.desc(), MessageModel.id.desc())

    # Берём на один элемент больше для проверки has_next
    result = await db.scalars(query.limit(limit + 1))
    messages = list(result.all())

    # Проверяем наличие следующей страницы
    has_next = calculate_has_more(messages, limit)

    # Убираем лишний элемент и разворачиваем при необходимости
    messages = trim_excess_item(messages, limit, reverse=False)

    # Формируем курсор для следующей страницы
    next_cursor = None

    if messages and has_next:
        oldest_msg = messages[-1]
        next_cursor = encode_cursor(oldest_msg.timestamp, oldest_msg.id)
        logger.debug(f"Сформирован курсор на основе сообщения {oldest_msg.id}")

    logger.info(
        f"Возвращено {len(messages)} сообщений, has_next={has_next}, next_cursor={'да' if next_cursor else 'нет'}"
    )

    return PaginatedResponse(
        items=[MessageSchemas.model_validate(message) for message in messages],
        next_cursor=next_cursor,
        has_next=has_next,
    )


@router.post("/stream_v2", status_code=status.HTTP_200_OK, summary="Добавить сообщение с поточным ответом (v2)")
async def add_message_stream_v2(
    conversation_id: UUID,
    request: MessageStreamRequest,
    current_user: UserModel = Depends(get_current_user),
    service: MessageService = Depends(get_message_service),
) -> StreamingResponse:
    """
    Добавить сообщение в беседу и получить поточный ответ (v2).

    Дополнительно поддерживает:
    - Выборочное использование mem0ai
    - Кастомные промпты
    - Настройку контекста (sliding window, memory facts)

    Args:
    - conversation_id: UUID беседы
    - request: Запрос с сообщением и настройками (MessageStreamRequest)
    - current_user: Текущий аутентифицированный пользователь
    - service: Сервис для обработки сообщений (MessageService)

    Returns:
    - StreamingResponse: Потоковый ответ сгенерированный LLM

    Raises:
    - HTTPException 422: Если content сообщения пустой
    - HTTPException 404: Если беседа или промпт не найдены
    - HTTPException 500: При ошибке генерации ответа
    """

    # Возвращаем streaming ответ
    try:
        data = await service.stream(
            conversation_id=conversation_id,
            message=request.message.content,
            message_role=request.message.role,
            mem0ai_on=request.mem0ai_on,
            mem0ai_save=request.mem0ai_save,
            prompt_id=request.prompt_id,
            model=request.model,
            sliding_window=request.sliding_window,
            memory_facts=request.memory_facts,
            user_id=current_user.id,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except LLMGenerationError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return StreamingResponse(service.stream_generator(stream_data=data), media_type="text/event-stream")
