import re
import time
from collections.abc import Awaitable
from uuid import UUID

from loguru import logger
from sqlalchemy import select

from app.database.postgres_db import AsyncSession
from app.depends.mem0_depends import get_memory
from app.models.messages import Message as MessageModel
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
        "\nФакты о пользователе:",
    ]
    for item in memory["results"]:
        if item["score"] >= 0.65:  # TODO: Лучше продумать работу системы со score
            data.append(" -" + item["memory"] + " - " + item["created_at"][:16])

    new_data = "\n".join(data)
    return new_data


async def get_conversation_history(prompt: str, db: AsyncSession, conversation_id: UUID, limit: int = 10) -> list[dict]:
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
    return [{"role": "system", "content": prompt}] + history


async def get_conversation_history_with_mem0(
    message: str, user_id: UUID, prompt: str, db: AsyncSession, conversation_id: UUID, limit: int = 10
) -> list[dict]:
    """Получить историю в формате для LLM"""
    start = time.time()

    db_start = time.time()
    result = await db.scalars(
        select(MessageModel)
        .where(MessageModel.conversation_id == conversation_id)
        .order_by(MessageModel.timestamp.desc())
        .limit(limit)
    )
    db_time = time.time() - db_start

    messages = result.all()

    mem_start = time.time()
    async with get_memory() as memory:
        facts = await memory.search(message, user_id=user_id, limit=10)
    mem_time = time.time() - mem_start

    total_time = time.time() - start
    logger.info(
        f"Кол-во Фактов: {len(facts['results'])}, БД: {db_time:.3f}s, Mem0: {mem_time:.3f}s, Всего: {total_time:.3f}s"
    )
    new_prompt = prompt + parse_facts_from_mem0(facts)

    # Нормализуем через Pydantic
    history = [HistoryMessage.model_validate(msg).model_dump(mode="json") for msg in reversed(messages)]

    # Преобразуем в формат для LLM
    return [{"role": "system", "content": new_prompt}] + history


async def save_message_to_db(db: AsyncSession, role: str, conversation_id: UUID, content: str, model: str) -> None:
    """Сохранение сообщения в БД"""
    message = MessageModel(conversation_id=conversation_id, role=role, content=content, model=model)
    db.add(message)
    await db.commit()


async def save_message_to_db_after_stream(
    result: Awaitable[str], db: AsyncSession, conversation_id: UUID, model: str
) -> None:
    """Сохранение сообщения от llm в БД после stream ответа"""

    full_response = await result

    assistant_message = MessageModel(
        conversation_id=conversation_id, role="assistant", content=full_response, model=model
    )

    db.add(assistant_message)

    await db.commit()
