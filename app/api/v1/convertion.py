import os
from typing import cast
from uuid import UUID

from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
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
from app.utils.utils import get_conversation_history


memory_local = AsyncMemory(config=custom_config)

router_v1 = APIRouter(prefix="/conversations", tags=["conversations"])

load_dotenv()


config = OpenAIConfig(
    model=os.getenv("MODEL"),
    temperature=0.6,
    api_key=os.getenv("OPENROUTER_API_KEY"),
    max_tokens=1000,
)  # TODO: Вынести формирование config подключения к llm в отдельную структуру чтобы пользователь мог менять настройки и прописывать свои API ключи

llm = AsyncOpenAILLM(config)


@router_v1.get("/", response_model=list[ConversationSchemas], status_code=status.HTTP_200_OK)
async def get_conversations(
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> list[ConversationModel]:
    """Получить все беседы пользователя"""
    result = await db.scalars(
        select(ConversationModel)
        .where(ConversationModel.user_id == current_user.id, ConversationModel.is_archived.is_(False))
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

    conversation = ConversationModel(user_id=current_user.id, title=conv_data.title or "New conversation")
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)

    return cast(ConversationModel, conversation)


@router_v1.get("/{conversation_id}/messages", response_model=list[MessageSchemas], status_code=status.HTTP_200_OK)
async def get_messages(
    conversation_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    limit: int = 50,
    db: AsyncSession = Depends(get_async_postgres_db),
) -> list[MessageModel]:  # TODO: Добавить пагинацию
    """Получить историю сообщений отдельной беседы"""
    await db.scalars(select(UserModel).where(UserModel.id == current_user.id))

    result = await db.scalars(
        select(MessageModel)
        .where(MessageModel.conversation_id == conversation_id, ConversationModel.is_archived.is_(False))
        .order_by(MessageModel.timestamp.desc())
        .limit(limit)
    )

    messages = cast(list[MessageModel], result.all())

    return list(reversed(messages))


@router_v1.post("/{conversation_id}/messages", status_code=status.HTTP_201_CREATED)
async def add_message(
    conversation_id: UUID,
    message: MessageCreate,
    background_tasks: BackgroundTasks,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> dict:
    """Добавить сообщение в беседу"""

    # Проверка доступа
    stmt = select(ConversationModel).where(
        ConversationModel.id == conversation_id,
        ConversationModel.user_id == current_user.id,
        ConversationModel.is_archived.is_(False),
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

    messages = [{"role": "assistant", "content": user_message.content}, {"role": "user", "content": assistant_response}]

    background_tasks.add_task(
        memory_local.add, messages, user_id=current_user.username, run_id=str(conversation.id)
    )  # TODO: Не работает должным образом выдаёт ошибки типизации у mem0ai

    return {"user_message": user_message.content, "assistant_message": assistant_response}


@router_v1.delete("/{conversation_id}", status_code=status.HTTP_200_OK)
async def delete_conversation(
    conversation_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> dict:
    """
    Выполняет мягкое удаление беседы по UUID
    """

    conversation = await db.get(ConversationModel, conversation_id)

    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    conversation.is_archived = True
    await db.commit()

    return {"message": "Conversation deleted"}
