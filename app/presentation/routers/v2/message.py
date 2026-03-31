from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from loguru import logger

from app.application.exceptions.conversation import ConversationNotFoundError
from app.application.exceptions.llm import LLMGenerationError
from app.application.exceptions.prompt import PromptNotFoundError
from app.application.schemas.message import MessageResponse as MessageSchemas
from app.application.schemas.message import MessageStreamRequest
from app.application.schemas.pagination import PaginatedResponse
from app.application.services.message_service import MessageService
from app.domain.models.user import User as UserModel
from app.infrastructure.llms.config import base_config_for_llm
from app.infrastructure.llms.openai import AsyncOpenAILLM
from app.infrastructure.persistence.pagination import (
    DEFAULT_PER_PAGE,
    MINIMUM_PER_PAGE,
    InvalidCursorError,
)
from app.presentation.dependencies import get_current_user, get_message_service


router = APIRouter(prefix="/{conversation_id}/messages", tags=["Messages"])


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
    service: MessageService = Depends(get_message_service),
) -> PaginatedResponse[MessageSchemas]:
    """
    Возвращает историю сообщений беседы с курсорной пагинацией.

    **Возможные ошибки:**
    - `400` — невалидный формат курсора
    - `404` — беседа не найдена или недоступна пользователю
    """
    try:
        return await service.get_user_messages(
            limit=limit,
            cursor=cursor,
            user_id=current_user.id,
            conversation_id=conversation_id,
        )
    except ConversationNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except InvalidCursorError as e:
        logger.warning("Невалидный курсор пользователя {}: {}", current_user.id, str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


@router.post("/stream_v2", status_code=status.HTTP_200_OK, summary="Добавить сообщение с поточным ответом (v2)")
async def add_message_stream_v2(
    conversation_id: UUID,
    request: MessageStreamRequest,
    current_user: UserModel = Depends(get_current_user),
    service: MessageService = Depends(get_message_service),
) -> StreamingResponse:
    """
    Добавляет сообщение в беседу и возвращает поточный ответ от LLM.

    Поддерживает кастомные промпты, настройку контекста (sliding window),
    и выборочное использование mem0ai для персонализации ответа.

    **Возможные ошибки:**
    - `404` — беседа или промпт не найдены
    - `422` — пустое content сообщения
    - `500` — ошибка генерации ответа LLM
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
