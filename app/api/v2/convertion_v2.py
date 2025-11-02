import os
from typing import cast
from uuid import UUID

from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from mem0 import AsyncMemory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.configs.llms.openai import OpenAIConfig
from app.configs.memory import custom_config
from app.depends.db_depends import get_async_postgres_db
from app.llms.openai import AsyncOpenAILLM
from app.models import Conversation as ConversationModel
from app.models import Message as MessageModel
from app.models import User as UserModel
from app.schemas.coversations import ConversationCreate
from app.schemas.coversations import ConversationResponse as ConversationSchemas
from app.schemas.messages import MessageCreate
from app.schemas.messages import MessageResponse as MessageSchemas
from app.utils.utils import get_conversation_history, save_message_to_db


memory_local = AsyncMemory(config=custom_config)

router_v2 = APIRouter(prefix="/conversations_v2", tags=["conversations_v2"])

load_dotenv()


config = OpenAIConfig(
    model=os.getenv("MODEL"),
    temperature=0.6,
    api_key=os.getenv("OPENROUTER_API_KEY"),
    max_tokens=1000,
)

llm = AsyncOpenAILLM(config)


@router_v2.get("/", response_model=list[ConversationSchemas], status_code=status.HTTP_200_OK)
async def get_conversation(
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> list[ConversationModel]:
    """Получить все беседы пользователя"""
    result = await db.scalars(
        select(ConversationModel)
        .where(ConversationModel.user_id == current_user.id)
        .order_by(ConversationModel.created_at.desc())
    )

    conversations = cast(list[ConversationModel], result.all())

    return conversations


@router_v2.post("/", response_model=ConversationSchemas, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    conv_data: ConversationCreate,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> ConversationModel:
    """Создать новую беседу"""

    conversation = ConversationModel(user_id=current_user.id, title=conv_data.title or "New conversation")
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)

    return cast(ConversationModel, conversation)


@router_v2.get("/{conversation_id}/messages", response_model=list[MessageSchemas], status_code=status.HTTP_200_OK)
async def get_messages(
    conversation_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    limit: int = 50,
    db: AsyncSession = Depends(get_async_postgres_db),
) -> list[MessageModel]:
    """Получить историю сообщений отдельной беседы"""
    await db.scalars(select(UserModel).where(UserModel.id == current_user.id))

    result = await db.scalars(
        select(MessageModel)
        .where(MessageModel.conversation_id == conversation_id)
        .order_by(MessageModel.timestamp.desc())
        .limit(limit)
    )

    messages = cast(list[MessageModel], result.all())

    return list(reversed(messages))


@router_v2.post("/{conversation_id}/message", response_model=MessageSchemas, status_code=status.HTTP_201_CREATED)
async def add_message(
    conversation_id: UUID,
    message: MessageCreate,
    background_tasks: BackgroundTasks,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> MessageModel:
    """Добавить сообщение в беседу"""

    # Проверка доступа
    result = await db.scalars(
        select(ConversationModel).where(
            ConversationModel.id == conversation_id, ConversationModel.user_id == current_user.id
        )
    )

    conversation = result.first()

    if not conversation:
        raise HTTPException(status_code=404, detail="Беседа не найдена")

    # Сохраняем сообщение пользователя
    user_message = MessageModel(
        conversation_id=conversation_id, role=message.role, content=message.content, model=os.getenv("MODEL")
    )
    db.add(user_message)

    # Получаем историю беседы
    history = await get_conversation_history(db, conversation_id)

    # Отправляем запрос к llm
    assistant_response = await llm.generate_response(history)

    # Сохраняем ответ ассистента
    assistant_message = MessageModel(
        conversation_id=conversation_id, role="assistant", content=assistant_response, model=os.getenv("MODEL")
    )
    db.add(assistant_message)

    await db.commit()

    # Передаём сообщение пользователя в mem0ai
    background_tasks.add_task(
        memory_local.add, messages=[message.model_dump()], user_id=current_user.username, run_id=str(conversation.id)
    )

    return assistant_message


@router_v2.post("/{conversation_id}/message/stream", status_code=status.HTTP_200_OK)
async def add_message_stream(
    conversation_id: UUID,
    message: MessageCreate,
    background_tasks: BackgroundTasks,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> StreamingResponse:
    """Добавить сообщение и получить стриминговый ответ"""

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
        raise HTTPException(status_code=404, detail="Беседа не найдена")

    # Сохраняем сообщение пользователя
    user_message = MessageModel(
        conversation_id=conversation_id, role=message.role, content=message.content, model=os.getenv("MODEL")
    )
    db.add(user_message)
    await db.commit()

    # Передаём сообщение на извлечение фактов в mem0ai
    background_tasks.add_task(
        memory_local.add, messages=[message.model_dump()], user_id=current_user.username, run_id=str(conversation_id)
    )

    # Получаем историю для контекста
    history = await get_conversation_history(db, conversation_id)

    stream, result_awaitable = await llm.generate_stream_response(messages=history)

    async def save_after_stream() -> None:
        full_response = await result_awaitable
        await save_message_to_db(db, conversation_id, full_response, model=os.getenv("MODEL"))

    background_tasks.add_task(save_after_stream)

    # Возвращаем streming ответ
    return StreamingResponse(stream, media_type="text/event-stream")


@router_v2.delete("/{conversation_id}", status_code=status.HTTP_200_OK)
async def delete_conversation(
    conversation_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> dict:
    """
    Полное удаление беседы по UUID из БД (Включая сообщения)
    """

    conversation = await db.get(ConversationModel, conversation_id)

    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    await db.delete(conversation)
    await db.commit()

    return {"message": "Conversation deleted"}
