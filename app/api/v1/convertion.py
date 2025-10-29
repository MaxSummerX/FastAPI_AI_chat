import os
from typing import cast
from uuid import UUID

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.configs.llms.openai import OpenAIConfig
from app.depends.db_depends import get_async_postgres_db
from app.llms.openai import AsyncOpenAILLM
from app.models import Conversation as ConversationModel
from app.models import Message as MessageModel
from app.models import User as UserModel
from app.schemas.coversations import ConversationCreate
from app.schemas.coversations import ConversationResponse as ConversationSchemas
from app.schemas.messages import MessageCreate
from app.schemas.messages import MessageResponse as MessageSchemas
from app.utils.utils import get_conversation_history


router_v1 = APIRouter(prefix="/conversations", tags=["conversations"])

load_dotenv()


config = OpenAIConfig(
    model=os.getenv("MODEL"),
    temperature=0.6,
    api_key=os.getenv("OPENROUTER_API_KEY"),
    max_tokens=1000,
)  # TODO: Вынести формирование config подключения к llm в отдельную структуру чтобы пользователь мог менять настройки и прописывать свои API ключи

llm = AsyncOpenAILLM(config)


@router_v1.post("/", response_model=ConversationSchemas, status_code=status.HTTP_200_OK)
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


# Добавление сообщения в беседу
@router_v1.post("/{conversation_id}/messages")
async def add_message(
    conversation_id: UUID,
    message: MessageCreate,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> dict:
    """Добавить сообщение в беседу"""

    # Проверка доступа
    stmt = select(ConversationModel).where(
        ConversationModel.id == conversation_id, ConversationModel.user_id == current_user.id
    )
    result = await db.scalars(stmt)
    conversation = result.first()

    if not conversation:
        raise HTTPException(status_code=404, detail="Беседа не найдена")

    # Сохраняем сообщение пользователя
    user_message = MessageModel(
        conversation_id=conversation_id, role=message.role, content=message.content, model=os.getenv("MODEL")
    )
    db.add(user_message)

    history = await get_conversation_history(db, conversation_id)

    assistant_response = await llm.generate_response(history)

    # Сохраняем ответ ассистента
    assistant_message = MessageModel(
        conversation_id=conversation_id, role="assistant", content=assistant_response, model=os.getenv("MODEL")
    )
    db.add(assistant_message)

    await db.commit()

    return {"user_message": user_message.content, "assistant_message": assistant_response}


@router_v1.get("/{conversation_id}/messages", response_model=list[MessageSchemas])
async def get_messages(
    conversation_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    limit: int = 50,
    db: AsyncSession = Depends(get_async_postgres_db),
) -> list[MessageSchemas]:
    """Получить историю сообщений"""
    await db.scalars(select(UserModel).where(UserModel.id == current_user.id))

    stmt = (
        select(MessageModel)
        .where(MessageModel.conversation_id == conversation_id)
        .order_by(MessageModel.timestamp.desc())
        .limit(limit)
    )

    result = await db.execute(stmt)
    messages = result.scalars().all()

    return list(reversed(messages))
