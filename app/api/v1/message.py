from typing import cast
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
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
from app.prompts.prompts_base import START_PROMPT
from app.schemas.messages import MessageCreate
from app.schemas.messages import MessageResponse as MessageSchemas
from app.utils.utils import (
    get_conversation_history,
    get_conversation_history_with_mem0,
    save_message_to_db_after_stream,
)


router_v1 = APIRouter(prefix="/{conversation_id}/messages")

memory_local = AsyncMemory(config=custom_config)

llm = AsyncOpenAILLM(base_config_for_llm)


@router_v1.get("/", response_model=list[MessageSchemas], status_code=status.HTTP_200_OK, tags=["Messages"])
async def get_messages(
    conversation_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    limit: int = 50,
    db: AsyncSession = Depends(get_async_postgres_db),
) -> list[MessageModel]:
    """Получить историю сообщений отдельной беседы"""
    logger.info(f"Запрос на получение беседы {conversation_id} пользователем {current_user.id}")
    await db.scalars(select(UserModel).where(UserModel.id == current_user.id))

    result = await db.scalars(
        select(MessageModel)
        .where(MessageModel.conversation_id == conversation_id)
        .order_by(MessageModel.timestamp)
        .limit(limit)
    )

    messages = cast(list[MessageModel], result.all())

    return list(messages)


@router_v1.post("/", response_model=MessageSchemas, status_code=status.HTTP_201_CREATED, tags=["Messages"])
async def add_message(
    conversation_id: UUID,
    message: MessageCreate,
    background_tasks: BackgroundTasks,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> MessageModel:
    """Добавить сообщение в беседу"""
    logger.info(f"Запрос на добавление сообщения в беседу {conversation_id} пользователем {current_user.id}")
    # Проверка доступа
    result = await db.scalars(
        select(ConversationModel).where(
            ConversationModel.id == conversation_id, ConversationModel.user_id == current_user.id
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

    # Получаем историю беседы
    history = await get_conversation_history(db, conversation_id, limit=10)

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

    return assistant_message


@router_v1.post("/stream", status_code=status.HTTP_200_OK, tags=["Messages"])
async def add_message_stream(
    conversation_id: UUID,
    message: MessageCreate,
    background_tasks: BackgroundTasks,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> StreamingResponse:
    """
    Добавить сообщение в беседу и получить стриминговый
    """
    logger.info(f"Запрос на добавления стримингового ответа в беседу {conversation_id} пользователем {current_user.id}")
    # Проверка доступа и что беседа существует
    result = await db.scalars(
        select(ConversationModel).where(
            ConversationModel.id == conversation_id,
            ConversationModel.user_id == current_user.id,
            ConversationModel.is_archived.is_(False),
        )
    )

    conversation = cast(ConversationModel, result.first())

    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    # Сохраняем сообщение пользователя
    user_message = MessageModel(
        conversation_id=conversation_id, role=message.role, content=message.content, model=llm.config.model
    )
    db.add(user_message)
    await db.commit()

    # Передаём сообщение на извлечение фактов в mem0ai
    background_tasks.add_task(
        memory_local.add,
        messages=[message.model_dump()],
        user_id=current_user.username,
        run_id=str(user_message.id),
    )

    # Получаем историю с системным промтом и релевантными фактами для контекста
    history = await get_conversation_history_with_mem0(
        message=message.content,
        user_name=current_user.username,
        prompt=START_PROMPT,
        db=db,
        conversation_id=conversation_id,
        limit=10,
    )

    # Передаём историю для генерации ответа
    stream, result_awaitable = await llm.generate_stream_response(messages=history)

    background_tasks.add_task(save_message_to_db_after_stream, result_awaitable, db, conversation_id, llm.config.model)

    logger.info(f"Сообщение добавлено в беседу {conversation_id}")
    # Возвращаем streming ответ
    return StreamingResponse(stream, media_type="text/event-stream")
