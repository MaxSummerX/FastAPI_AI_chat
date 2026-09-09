import json
from typing import Any
from uuid import UUID

from loguru import logger

from app.application.prompts.parsing_category import PARSE_CATEGORY
from app.domain.enums.fact import FactSource
from app.domain.models.fact import Fact
from app.domain.repositories.facts import IFactRepository
from app.domain.repositories.messages import IMessageRepository
from app.domain.services.llm import ILLMService
from app.domain.services.memory import IMemoryService


class FactImportService:
    """ETL-импорт фактов из mem0 (Qdrant) в PostgreSQL."""

    def __init__(
        self,
        fact_repo: IFactRepository,
        memory_service: IMemoryService,
        message_repo: IMessageRepository,
        llm_service: ILLMService,
    ) -> None:
        self.fact_repo = fact_repo
        self.memory_service = memory_service
        self.message_repo = message_repo
        self.llm_service = llm_service

    async def import_from_mem0ai_to_postgres_db(
        self,
        user_id: UUID,
    ) -> None:
        """
        Импортировать факты из mem0ai в PostgreSQL.

        Процесс:
        1. Получает все факты EXTRACTED из mem0ai для пользователя
        2. Собирает валидные message_id и строит отображения:
           - fact_by_memory: {memory_content: fact_data}
           - message_id_by_memory: {memory_content: message_id}
        3. Батч-запросом получает все сообщения из PostgreSQL
        4. Батч-запросом проверяет какие факты уже существуют
        5. Для каждого нового факта:
           - Пропускает если факт уже существует
           - Пропускает если сообщение не найдено
           - Если нет категории в metadata → вызывает LLM для категоризации
           - Создаёт Fact с данными из Qdrant
        6. Сохраняет все новые факты одним батч-коммитом

        Оптимизация N+1:
        - Вместо 2N запросов использует 2 батч-запроса (messages + existing_facts)
        - Использует set/dict для O(1) поиска вместо запросов в цикле

        Args:
            user_id: UUID пользователя для импорта фактов

        Returns:
            None

        Note:
            - Метод для background task (вызывается из presentation/background.py)
            - Пропускает факты с невалидным run_id
            - Категоризирует факты через LLM если нет категории в metadata
        """

        # Запрашиваем все EXTRACTED факты из mem0ai для пользователя
        facts = await self.memory_service.get_all(
            user_id=str(user_id), filters={"source_type": FactSource.EXTRACTED.value}
        )

        # Строим отображения для батч-обработки
        fact_by_memory: dict[str, Any] = {}  # {memory_content: fact_data}
        message_id_by_memory: dict[str, UUID] = {}  # {memory_content: message_id}
        message_ids: list[UUID] = []  # список всех message_id для батч-запроса

        # Собираем факты в отображения, фильтруя невалидные UUID
        for fact in facts["results"]:
            try:
                message_id = UUID(fact["run_id"])  # извлекаем message_id из run_id
                memory_content = fact["memory"]  # текст факта
                message_ids.append(message_id)
                fact_by_memory[memory_content] = fact  # для быстрого O(1) доступа
                message_id_by_memory[memory_content] = message_id
            except ValueError:
                logger.warning(f"Невалидный run_id: {fact.get('run_id')}")
                continue

        # Ранний возврат если нет валидных данных
        if not message_ids:
            logger.info("Нет валидных фактов для импорта")
            return

        # Батч-запросы к PostgreSQL
        # Запрос 1: получаем все сообщения одним запросом (вместо N отдельных)
        messages_result = await self.message_repo.get_messages_by_id(message_ids)
        messages_by_id = {msg.id: msg for msg in messages_result}  # {message_id: message}

        # Запрос 2: проверяем существующие факты одним запросом
        existing_contents = list(fact_by_memory.keys())  # все memory_content для проверки
        existing_facts_result = await self.fact_repo.get_existing_facts(
            source=FactSource.EXTRACTED, content=existing_contents
        )
        existing_fact_contents = {fact.content for fact in existing_facts_result}  # set для O(1)

        # Обработка фактов
        new_facts = []
        skipped_messages = 0
        skipped_facts = 0

        for memory_content, fact in fact_by_memory.items():
            message_id = message_id_by_memory[memory_content]

            # Пропускаем если факт уже существует в PostgreSQL
            if memory_content in existing_fact_contents:
                logger.info(f"Факт уже есть: {memory_content[:50]}...")
                skipped_facts += 1
                continue

            # Пропускаем если сообщение не найдено (было удалено)
            message_db = messages_by_id.get(message_id)
            if not message_db:
                logger.info(f"Сообщение не найдено: {message_id}")
                skipped_messages += 1
                continue

            # Определяем категорию факта
            if fact["metadata"] is None or "category" not in fact["metadata"]:
                # Категория не задана → вызываем LLM для классификации
                message = [
                    {"role": "system", "content": PARSE_CATEGORY},
                    {"role": "user", "content": fact["memory"]},
                ]
                response = await self.llm_service.generate_response(message, response_format={"type": "json_object"})
                response_str = str(response) if isinstance(response, dict) else response
                category_data: dict[str, Any] = json.loads(response_str)
                logger.info(f"Категория из LLM: {category_data}")

                category_value = category_data.get("category")

                if category_value is None:
                    logger.info(f"Категория не определена для факта: {fact['memory']}")
                    continue
            else:
                # Категория есть в metadata → используем её
                category_value = fact["metadata"]["category"]
                logger.info(f"Категория из metadata: {category_value}")

            # Создаём новый факт для PostgreSQL
            new_fact = Fact(
                user_id=user_id,
                content=fact["memory"],
                category=category_value,
                source_type=FactSource.EXTRACTED,
                source_conversation_id=message_db.conversation_id,  # ссылка на беседу
                source_message_id=message_db.id,  # ссылка на сообщение
                mem0_id=fact["id"],  # ID факта в Qdrant
            )
            new_facts.append(new_fact)

        # Сохраняем все новые факты одним батч-коммитом
        if new_facts:
            await self.fact_repo.save_all(new_facts)
        logger.info(
            f"Импорт завершён: создано={len(new_facts)}, пропущено фактов={skipped_facts}, пропущено сообщений={skipped_messages}"
        )
