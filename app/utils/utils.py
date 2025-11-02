import re
from uuid import UUID

from sqlalchemy import select

from app.database.postgres_db import AsyncSession
from app.models.messages import Message as MessageModel


def extract_json(text: str) -> str:
    """
    Извлекает JSON-контент из строки, удаляя тройные обратные кавычки и необязательный тег «json», если он есть.
    Если блок кода не найден, возвращает текст как есть.
    """
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        json_str = text

    return json_str


async def get_conversation_history(db: AsyncSession, conversation_id: UUID, limit: int = 10) -> list[dict]:
    """Получить историю в формате для LLM"""

    result = await db.scalars(
        select(MessageModel)
        .where(MessageModel.conversation_id == conversation_id)
        .order_by(MessageModel.timestamp.desc())
        .limit(limit)
    )

    messages = result.all()

    # Преобразуем в формат для LLM
    return [{"role": msg.role, "content": msg.content} for msg in reversed(messages)]


async def save_message_to_db(db: AsyncSession, conversation_id: UUID, content: str, model: str) -> None:
    """Сохранение сообщения от llm в БД"""
    assistant_message = MessageModel(conversation_id=conversation_id, role="assistant", content=content, model=model)
    db.add(assistant_message)
    await db.commit()
