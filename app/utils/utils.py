import re
from collections.abc import Awaitable
from uuid import UUID

from sqlalchemy import select

from app.database.postgres_db import AsyncSession
from app.depends.mem0_depends import get_memory
from app.models.messages import Message as MessageModel
from app.prompts.prompts_base import BASE_PROMPT
from app.schemas.messages import HistoryMessage


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


def parse_facts_from_mem0(memory: dict) -> str:
    data = [
        "Факты\n",
    ]
    for item in memory["results"]:
        if item["score"] >= 0.75:
            data.append(" -" + item["memory"] + " - " + item["created_at"][:16])

    new_data = "\n".join(data)
    return new_data


async def get_conversation_history(db: AsyncSession, conversation_id: UUID, limit: int = 10) -> list[dict]:
    """Получить историю в формате для LLM"""

    result = await db.scalars(
        select(MessageModel)
        .where(MessageModel.conversation_id == conversation_id)
        .order_by(MessageModel.timestamp.desc())
        .limit(limit)
    )

    messages = result.all()

    # Нормализуем через Pydantic
    history = [HistoryMessage.model_validate(msg).model_dump(mode="json") for msg in reversed(messages)]

    # Преобразуем в формат для LLM
    return [{"role": "system", "content": BASE_PROMPT}] + history


async def get_conversation_history_with_mem0(
    message: str, user_name: str, prompt: str, db: AsyncSession, conversation_id: UUID, limit: int = 10
) -> list[dict]:
    """Получить историю в формате для LLM"""

    result = await db.scalars(
        select(MessageModel)
        .where(MessageModel.conversation_id == conversation_id)
        .order_by(MessageModel.timestamp.desc())
        .limit(limit)
    )

    messages = result.all()

    async with get_memory() as memory:
        memory = await memory.search(message, user_id=str(user_name), limit=10)

    new_prompt = prompt + parse_facts_from_mem0(memory)

    # Нормализуем через Pydantic
    history = [HistoryMessage.model_validate(msg).model_dump(mode="json") for msg in reversed(messages)]

    # Преобразуем в формат для LLM
    return [{"role": "system", "content": new_prompt}] + history


async def save_message_to_db(db: AsyncSession, conversation_id: UUID, content: str, model: str) -> None:
    """Сохранение сообщения от llm в БД"""
    assistant_message = MessageModel(conversation_id=conversation_id, role="assistant", content=content, model=model)
    db.add(assistant_message)
    await db.commit()


async def save_message_to_db_after_stream(
    result: Awaitable[str], db: AsyncSession, conversation_id: UUID, model: str
) -> None:
    """Сохранение сообщения от llm в БД после стримингого ответа"""

    full_response = await result

    assistant_message = MessageModel(
        conversation_id=conversation_id, role="assistant", content=full_response, model=model
    )

    db.add(assistant_message)

    await db.commit()
