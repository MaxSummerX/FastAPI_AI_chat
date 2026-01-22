from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from loguru import logger
from mem0 import AsyncMemory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.configs.llm_config import base_config_for_llm
from app.configs.memory import custom_config
from app.depends.db_depends import get_async_postgres_db
from app.llms.openai import AsyncOpenAILLM
from app.models import Conversation as ConversationModel
from app.models import Message as MessageModel
from app.models import User as UserModel
from app.models.prompts import Prompts as PromptModel
from app.prompts.prompts_base import START_PROMPT
from app.schemas.messages import MessageCreate
from app.schemas.messages import MessageResponse as MessageSchemas
from app.schemas.pagination import PaginatedResponse
from app.utils.utils import (
    get_conversation_history,
    get_conversation_history_with_mem0,
    save_message_to_db_after_stream,
)
from app.utils.utils_for_pagination import (
    calculate_has_more,
    decode_cursor,
    encode_cursor,
    trim_excess_item,
    validate_pagination_limit,
)


router = APIRouter(prefix="/{conversation_id}/messages", tags=["Messages_v2"])

memory_local = AsyncMemory(config=custom_config)
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


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Добавить сообщение в беседу",
)
async def add_message(
    conversation_id: UUID,
    message: MessageCreate,
    background_tasks: BackgroundTasks,
    prompt_id: UUID | None = None,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> MessageSchemas:
    """
    Добавить сообщение в беседу и получить ответ от ассистента.

    Args:
        conversation_id: UUID беседы
        message: Сообщение пользователя (role, content)
        background_tasks: FastAPI background tasks
        prompt_id: Опциональный ID кастомного промпта
        current_user: Текущий пользователь
        db: Сессия БД

    Returns:
        MessageModel: Ответ ассистента

    Raises:
        HTTPException 404: Если беседа или промпт не найдены
    """
    logger.info(f"Запрос на добавление сообщения в беседу {conversation_id} пользователем {current_user.id}")

    # Проверка доступа и существования беседы
    conversation_result = await db.scalars(
        select(ConversationModel).where(
            ConversationModel.id == conversation_id, ConversationModel.user_id == current_user.id
        )
    )

    conversation = conversation_result.first()

    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # Валидация: контент не должен быть пустым
    if not message.content or not message.content.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message content cannot be empty")

    # Получаем промпт с дополнительными проверками
    if not prompt_id:
        prompt = START_PROMPT
    else:
        prompt_result = await db.scalars(
            select(PromptModel).where(
                PromptModel.id == prompt_id,
                PromptModel.user_id == current_user.id,
                PromptModel.is_active.is_(True),
            )
        )

        prompt_obj = prompt_result.first()
        if not prompt_obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found")  # зачем еще проверка
        prompt = prompt_obj.content

    # Сохраняем сообщение пользователя
    user_message = MessageModel(
        conversation_id=conversation_id, role=message.role, content=message.content, model=llm.config.model
    )
    db.add(user_message)
    await db.flush()  # Получаем ID сообщения для background task

    # Получаем историю беседы
    history = await get_conversation_history(prompt, db, conversation_id, limit=10)

    # Отправляем запрос к llm
    assistant_response = await llm.generate_response(history)

    # Сохраняем ответ ассистента
    assistant_message = MessageModel(
        conversation_id=conversation_id, role="assistant", content=assistant_response, model=llm.config.model
    )
    db.add(assistant_message)

    await db.commit()

    # Передаём сообщение пользователя в mem0ai
    background_tasks.add_task(
        memory_local.add, messages=[message.model_dump()], user_id=current_user.username, run_id=str(user_message.id)
    )

    logger.info(f"Сообщение добавлено в беседу {conversation_id}")

    return MessageSchemas.model_validate(assistant_message)


@router.post("/stream", status_code=status.HTTP_200_OK, summary="Добавить сообщение с поточным ответом")
async def add_message_stream(
    conversation_id: UUID,
    message: MessageCreate,
    background_tasks: BackgroundTasks,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> StreamingResponse:
    """
    Добавить сообщение в беседу и получить поточный ответ от ассистента.

    Ответ передаётся в реальном времени через Server-Sent Events (SSE).

    Args:
        conversation_id: UUID беседы
        message: Сообщение пользователя
        background_tasks: FastAPI background tasks
        current_user: Текущий пользователь
        db: Сессия БД

    Returns:
        StreamingResponse: Потоковый ответ с текстом события

    Raises:
        HTTPException 404: Если беседа не найдена
    """
    logger.info(f"Запрос на добавление стримингового ответа в беседу {conversation_id} пользователем {current_user.id}")

    # Проверка доступа и что беседа существует
    result = await db.scalars(
        select(ConversationModel).where(
            ConversationModel.id == conversation_id,
            ConversationModel.user_id == current_user.id,
            ConversationModel.is_archived.is_(False),
        )
    )

    conversation = result.first()

    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # Сохраняем сообщение пользователя
    user_message = MessageModel(
        conversation_id=conversation_id, role=message.role, content=message.content, model=llm.config.model
    )
    db.add(user_message)
    await db.flush()  # Получаем ID сообщения для background task
    await db.commit()

    # Передаём сообщение на извлечение фактов в mem0ai
    background_tasks.add_task(
        memory_local.add,
        messages=[message.model_dump()],
        user_id=str(current_user.id),
        run_id=str(user_message.id),
    )

    # Получаем историю с системным промптом и релевантными фактами для контекста
    history = await get_conversation_history_with_mem0(
        message=message.content,
        user_id=current_user.id,
        prompt=START_PROMPT,
        db=db,
        conversation_id=conversation_id,
        limit=10,
    )

    # Передаём историю для генерации ответа
    stream, result_awaitable = await llm.generate_stream_response(messages=history)

    background_tasks.add_task(save_message_to_db_after_stream, result_awaitable, db, conversation_id, llm.config.model)

    logger.info(f"Стриминговый ответ запущен для беседы {conversation_id}")

    # Возвращаем streaming ответ
    return StreamingResponse(stream, media_type="text/event-stream")


@router.post("/stream_v2", status_code=status.HTTP_200_OK, summary="Добавить сообщение с поточным ответом (v2)")
async def add_message_stream_v2(
    conversation_id: UUID,
    message: MessageCreate,
    background_tasks: BackgroundTasks,
    mem0ai_on: bool = False,
    prompt_id: UUID | None = None,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> StreamingResponse:
    """
    Добавить сообщение в беседу и получить улучшенный поточный ответ.

    Дополнительно поддерживает:
    - Выборочное использование mem0ai
    - Кастомные промпты

    Args:
        conversation_id: UUID беседы
        message: Сообщение пользователя
        background_tasks: FastAPI background tasks
        mem0ai_on: Использовать ли mem0ai для контекста
        prompt_id: ID кастомного промпта
        current_user: Текущий пользователь
        db: Сессия БД

    Returns:
        StreamingResponse: Потоковый ответ

    Raises:
        HTTPException 400: Если content пустой
        HTTPException 404: Если беседа или промпт не найдены
        HTTPException 500: При ошибке генерации ответа
    """
    logger.info(
        f"Запрос на добавление стримингового ответа v2 в беседу {conversation_id} пользователем {current_user.id}"
    )

    # Проверка существования беседы
    conversation_result = await db.scalars(
        select(ConversationModel).where(
            ConversationModel.id == conversation_id, ConversationModel.user_id == current_user.id
        )
    )
    conversation = conversation_result.first()

    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    if not message.content or not message.content.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Message content cannot be empty")

    # Сохраняем сообщение пользователя
    user_message = MessageModel(
        conversation_id=conversation_id, role=message.role, content=message.content, model=llm.config.model
    )
    db.add(user_message)
    await db.flush()  # Получаем ID сообщения для background task
    await db.commit()

    # Получаем промпт с улучшенными проверками
    if prompt_id:
        prompt_result = await db.scalars(
            select(PromptModel).where(
                PromptModel.id == prompt_id,
                PromptModel.user_id == current_user.id,
                PromptModel.is_active.is_(True),
            )
        )

        prompt = prompt_result.first()
        logger.info(f"Поиск промпта: id={prompt_id}, найден={prompt is not None}")
        if not prompt:
            logger.warning(f"Промпт не найден: id={prompt_id}, пользователь={current_user.id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Prompt with id={prompt_id} not found or not accessible"
            )

        prompt_content = prompt.content
    else:
        prompt_content = START_PROMPT

    if not mem0ai_on:
        history = await get_conversation_history(
            prompt=prompt_content, db=db, conversation_id=conversation_id, limit=10
        )
    else:
        # Получаем историю с системным промптом и релевантными фактами для контекста
        history = await get_conversation_history_with_mem0(
            message=message.content,
            user_id=current_user.id,
            prompt=prompt_content,
            db=db,
            conversation_id=conversation_id,
            limit=10,
        )

    # Передаём историю для генерации ответа
    try:
        stream, result_awaitable = await llm.generate_stream_response(messages=history)
    except Exception as e:
        logger.error(f"Ошибка при генерации стримингового ответа: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate response"
        ) from e

    # Создаём фоновую задачу для работы mem0ai
    background_tasks.add_task(
        memory_local.add,
        messages=[message.model_dump()],
        user_id=str(current_user.id),
        run_id=str(user_message.id),
    )

    # Сохраняем сообщение от llm в фоне
    background_tasks.add_task(save_message_to_db_after_stream, result_awaitable, db, conversation_id, llm.config.model)

    logger.info(f"Сообщение добавлено в беседу {conversation_id}, стриминг запущен")

    # Возвращаем streaming ответ
    return StreamingResponse(stream, media_type="text/event-stream")
