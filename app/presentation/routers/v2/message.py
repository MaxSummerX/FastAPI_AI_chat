from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.exceptions.conversation import ConversationNotFoundError
from app.application.exceptions.llm import LLMGenerationError
from app.application.exceptions.prompt import PromptNotFoundError
from app.application.schemas.message import MessageResponse as MessageSchemas
from app.application.schemas.message import MessageStreamRequest
from app.application.schemas.pagination import PaginatedResponse
from app.domain.models.conversation import Conversation as ConversationModel
from app.domain.models.message import Message as MessageModel
from app.domain.models.user import User as UserModel
from app.infrastructure.database.dependencies import get_db
from app.infrastructure.llms.config import base_config_for_llm
from app.infrastructure.llms.openai import AsyncOpenAILLM
from app.infrastructure.persistence.pagination import (
    DEFAULT_PER_PAGE,
    MINIMUM_PER_PAGE,
    InvalidCursorError,
    paginate_with_cursor,
)
from app.presentation.dependencies import get_current_user
from app.services.message_service import MessageService, get_message_service


router = APIRouter(prefix="/{conversation_id}/messages", tags=["Messages_v2"])


llm = AsyncOpenAILLM(base_config_for_llm)


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
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[MessageSchemas]:
    """
    Получить историю сообщений с курсорной пагинацией.
    """
    logger.info(f"Запрос сообщений беседы {conversation_id} от пользователя {current_user.id}")

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

    try:
        messages, next_cursor, has_next = await paginate_with_cursor(
            db=db,
            query=query,
            cursor=cursor,
            limit=limit,
            model=MessageModel,
            timestamp_field="timestamp",  # MessageModel использует поле timestamp, не created_at
        )
    except InvalidCursorError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None

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
    - HTTPException 422: Если content сообщения пустой (Pydantic validation)
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
    except (ConversationNotFoundError, PromptNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except LLMGenerationError as e:
        raise HTTPException(status_code=500, detail=str(e)) from None

    return StreamingResponse(service.stream_generator(stream_data=data), media_type="text/event-stream")
