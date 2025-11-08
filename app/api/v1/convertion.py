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
from app.schemas.coversations import ConversationCreate
from app.schemas.coversations import ConversationResponse as ConversationSchemas
from app.schemas.messages import MessageCreate
from app.schemas.messages import MessageResponse as MessageSchemas
from app.utils.utils import (
    get_conversation_history,
    get_conversation_history_with_mem0,
    save_message_to_db_after_stream,
)


router_v1 = APIRouter(prefix="/conversations", tags=["Conversations"])

memory_local = AsyncMemory(config=custom_config)

llm = AsyncOpenAILLM(base_config_for_llm)


@router_v1.get("/", response_model=list[ConversationSchemas], status_code=status.HTTP_200_OK)
async def get_conversation(
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> list[ConversationModel]:
    """Получить все беседы пользователя"""
    logger.info(f"Запрос на получение бесед пользователя {current_user.id}")
    result = await db.scalars(
        select(ConversationModel)
        .where(ConversationModel.user_id == current_user.id)
        .order_by(ConversationModel.created_at.desc())
    )

    conversations = cast(list[ConversationModel], result.all())

    return conversations


@router_v1.post("/", response_model=ConversationSchemas, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    conv_data: ConversationCreate,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> ConversationModel:
    """Создать новую беседу"""
    logger.info(f"Запрос на создание беседы пользователем {current_user.id}")
    conversation = ConversationModel(user_id=current_user.id, title=conv_data.title or "New conversation")
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)

    logger.info(f"Создана беседа {conversation.id} для пользователя {current_user.id}")

    return cast(ConversationModel, conversation)


@router_v1.get("/{conversation_id}/messages", response_model=list[MessageSchemas], status_code=status.HTTP_200_OK)
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


@router_v1.post("/{conversation_id}/message", response_model=MessageSchemas, status_code=status.HTTP_201_CREATED)
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


@router_v1.post("/{conversation_id}/message/stream", status_code=status.HTTP_200_OK)
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


@router_v1.delete("/{conversation_id}", status_code=status.HTTP_200_OK)
async def delete_conversation(
    conversation_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> dict:
    """
    Полное удаление беседы по UUID из БД (Включая сообщения)
    """
    logger.info(f"Запрос на полное удаление беседы {conversation_id} пользователя {current_user.id}")
    conversation = await db.get(ConversationModel, conversation_id)

    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    await db.delete(conversation)
    await db.commit()

    logger.info(f"Удалён беседа {conversation_id}")

    return {"message": "Conversation deleted"}
