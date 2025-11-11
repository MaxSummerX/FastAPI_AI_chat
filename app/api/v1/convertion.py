from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import message
from app.auth.dependencies import get_current_user
from app.depends.db_depends import get_async_postgres_db
from app.models import Conversation as ConversationModel
from app.models import User as UserModel
from app.schemas.coversations import ConversationCreate
from app.schemas.coversations import ConversationResponse as ConversationSchemas


router_v1 = APIRouter(prefix="/conversations")

router_v1.include_router(message.router_v1)


@router_v1.get("/", response_model=list[ConversationSchemas], status_code=status.HTTP_200_OK, tags=["conversations"])
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


@router_v1.post("/", response_model=ConversationSchemas, status_code=status.HTTP_201_CREATED, tags=["conversations"])
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


@router_v1.delete("/{conversation_id}", status_code=status.HTTP_200_OK, tags=["conversations"])
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
