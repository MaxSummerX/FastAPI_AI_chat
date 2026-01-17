import json
import uuid
from typing import Any, cast

from loguru import logger
from mem0 import AsyncMemory
from sqlalchemy import select

from app.configs.llm_config import parse_llm_config
from app.configs.memory import custom_config
from app.database.postgres_db import async_session_maker
from app.llms.openai import AsyncOpenAILLM
from app.models import Conversation as ConversationModel
from app.models import Fact as FactModel
from app.models import Message as MessageModel
from app.prompts.prompts_for_parse import PARSE_CATEGORY


llm = AsyncOpenAILLM(parse_llm_config)
memory_local = AsyncMemory(config=custom_config)


# TODO: ВАЖНО!!! user_id в postgres храниться в UUID, а mem0ai принимает str
async def import_from_mem0ai_to_postgres_db(user_id: str) -> None:
    """
    Импортирование фактов из mem0ai в Postgres
    """

    # Запрашиваем все факты о пользователе
    facts = await memory_local.get_all(user_id=user_id)

    # Через цикл проверяем все факты
    for fact in facts["results"]:
        # Выделяем из факта id беседы
        message_id = uuid.UUID(fact["run_id"])

        # Подключаем асинхронную сессию
        async with async_session_maker() as session:
            # Подгружаем из бд соответсвующую сообщение
            message_db = await session.scalar(select(MessageModel).where(MessageModel.id == message_id))

            conversation = await session.scalar(
                select(ConversationModel).where(ConversationModel.id == message_db.conversation_id)
            )

            # Проверяем что беседа существует
            if not message_db:
                logger.info(f"Conversation не найдена: {message_id}")
                continue

            # Подгружаем из бд соответсвующую факт
            existing_fact = await session.scalar(select(FactModel).where(FactModel.content == fact["memory"]))

            # Проверяем наличие факта
            if existing_fact:
                # Факт уже существует, пропускаем
                logger.info(f"Факт уже есть: {existing_fact.id}")
                continue
            # Если факта нет запускаем категоризацию через llm
            else:
                # Проверяем что метаданные пусты или в них нет category
                if fact["metadata"] is None or "category" not in fact["metadata"]:
                    # Формируем сообщение для llm
                    message = [
                        {"role": "system", "content": PARSE_CATEGORY},
                        {"role": "user", "content": fact["memory"]},
                    ]
                    # Отравляем в модель с указанием требуемого формата ответа
                    response = await llm.generate_response(message, response_format={"type": "json_object"})
                    # Конвертируем ответ
                    response_str = cast(str, response)
                    category_data: dict[str, Any] = json.loads(response_str)
                    logger.info(f"Категория из LLM: {category_data}")

                    # Извлекаем значение категории
                    category_value = category_data.get("category")

                    # Проверяем что категория не пустая
                    if category_value is None:
                        logger.info(f"Категория не определена для факта: {fact['memory']}")
                        continue
                else:
                    # Если метаданные имеют категорию, то передаём их
                    category_value = fact["metadata"]["category"]
                    logger.info(f"Категория из metadata: {category_value}")

                # Создавай новый факт
                new_fact = FactModel(
                    user_id=conversation.user_id,
                    content=fact["memory"],
                    category=category_value,
                    source_type="imported",
                    source_conversation_id=conversation.id,
                    source_message_id=message_db.id,
                )
                # Добавляем в сессию
                session.add(new_fact)
                # Сохраняем
                await session.commit()
                logger.info(f"✓ Факт создан: {new_fact.id}")


async def import_from_postgres_db_to_mem0ai() -> None:
    pass
