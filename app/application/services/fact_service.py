import json
from typing import Any
from uuid import UUID

from loguru import logger

from app.application.exceptions.fact import FactCreationException, FactNotFoundException, UserProvidedException
from app.application.schemas.fact import FactCreate, FactResponse
from app.application.schemas.pagination import PaginatedResponse
from app.domain.enums.fact import FactCategory, FactSource
from app.domain.models.fact import Fact
from app.infrastructure.memory.mem0_service import IMemoryService
from app.infrastructure.persistence.sqlalchemy.fact_repository import IFactRepository
from app.infrastructure.persistence.sqlalchemy.message_repository import IMessageRepository


class FactService:
    """Сервис для управления фактами пользователей."""

    def __init__(
        self, fact_repo: IFactRepository, memory_service: IMemoryService, message_repo: IMessageRepository
    ) -> None:
        self.fact_repo = fact_repo
        self.memory_service = memory_service
        self.message_repo = message_repo

    async def get_user_facts(
        self,
        category: FactCategory | None,
        source: FactSource | None,
        limit: int,
        cursor: str | None,
        user_id: UUID,
        include_archived: bool,
    ) -> PaginatedResponse[FactResponse]:
        """
        Получить факты пользователя с курсорной пагинацией.

        Args:
            category: Фильтр по категории фактов (опционально)
            limit: Максимальное количество фактов на странице
            cursor: Курсор из предыдущего ответа для следующей страницы
            source: Фильтр по источнику фактов (опционально)
            user_id: UUID пользователя
            include_archived: Включать ли архивные факты

        Returns:
            PaginatedResponse с фактами и метаданными пагинации
        """
        logger.debug(
            "Запрос на получение фактов пользователя {} с пагинацией: limit={}, cursor={}",
            user_id,
            limit,
            "да" if cursor else "нет",
        )
        facts, next_cursor, has_next = await self.fact_repo.get_paginated(
            user_id=user_id,
            cursor=cursor,
            limit=limit,
            category=category,
            source=source,
            include_archived=include_archived,
        )
        logger.debug(
            "Возвращено {} фактов, has_next={}, next_cursor={}",
            len(facts),
            has_next,
            "да" if next_cursor else "нет",
        )

        return PaginatedResponse(
            items=[FactResponse.model_validate(fact) for fact in facts],
            next_cursor=next_cursor,
            has_next=has_next,
        )

    async def get_user_fact_by_id(self, fact_id: UUID, user_id: UUID) -> FactResponse:
        """
        Получить факт по идентификатору.

        Args:
            fact_id: ID факта
            user_id: ID пользователя (для проверки владения)

        Returns:
            FactResponse с данными факта

        Raises:
            FactNotFoundException: Если факт не найден
        """
        fact = await self.fact_repo.get_by_id(fact_id=fact_id, user_id=user_id)

        if not fact:
            logger.warning("Факт не найден: fact_id={}, user_id={}", fact_id, user_id)
            raise FactNotFoundException(f"Fact {fact_id} not found")

        return FactResponse.model_validate(fact)

    async def create_user_fact(
        self,
        user_id: UUID,
        data: FactCreate,
    ) -> None:
        """
        Создать факт в PostgreSQL и mem0ai.

        Процесс:
          1. Добавляет факт в Qdrant через mem0ai (infer=False - без связей в Neo4j)
          2. Получает mem0_id из ответа Qdrant
          3. Создаёт запись в PostgreSQL с mem0_id
          4. При сбое PG - компенсация: вектор удаляется из Qdrant

        Args:
            user_id: UUID пользователя
            data: Данные для создания факта

        Returns:
            None (функция для background task)

        Raises:
            FactCreationException: Ошибка внешней системы памяти (mem0ai/Qdrant) -> 502
        """
        category = data.category if data.category else FactCategory.PERSONAL

        mem0_metadata = {
            "source_type": FactSource.USER_PROVIDED.value,
            "category": category.value,
        }

        if data.metadata_:
            mem0_metadata.update(data.metadata_)
        try:
            result = await self.memory_service.add(
                messages=data.content, user_id=str(user_id), infer=False, metadata=mem0_metadata
            )
        except FactCreationException:
            raise
        except Exception as e:
            logger.exception(f"Ошибка mem0ai/Qdrant при создании факта | user_id = {user_id}")
            raise FactCreationException("Memory service error while creating fact") from e

        try:
            mem0_id = result["results"][0]["id"]
        except (KeyError, IndexError, ValueError, TypeError) as e:
            logger.error("mem0ai вернул неожиданный ответ: {!r}", result)
            raise FactCreationException("Memory service returned unexpected response") from e

        new_fact = Fact(
            user_id=user_id,
            content=data.content,
            category=category,
            source_type=FactSource.USER_PROVIDED,
            confidence=data.confidence,
            metadata_=data.metadata_,
            mem0_id=UUID(mem0_id),  # Конвертируем строку в UUID
        )

        try:
            await self.fact_repo.save(new_fact)
        except Exception:
            try:
                await self.memory_service.delete(memory_id=str(mem0_id))
            except Exception:
                logger.exception(f"Вектор-сирота {mem0_id} остался в Qdrant")
            raise

        logger.info(f"Факт {new_fact.id} создан с mem0_id {new_fact.mem0_id}")

    async def update_user_fact(
        self,
        user_id: UUID,
        fact_id: UUID,
        data: FactCreate,
    ) -> None:
        """
        Обновить факт в PostgreSQL и mem0ai.

        Процесс:
        1. Добавить НОВЫЙ вектор в Qdrant (старый пока жив)
        2. Обновить PG: mem0_id -> новый (сбой -> компенсация: удалить новый вектор)
        3. Удалить СТАРЫЙ вектор (сбой -> безвредный сирота в логе)

        Args:
            user_id: UUID пользователя
            fact_id: ID факта для обновления
            data: Новые данные факта
        Returns:
            None (функция для background task)

        Raises:
            FactNotFoundException: Факт не найден или недоступен
            UserProvidedException: Факт не создан пользователем (нельзя редактировать)
            ValueError: У факта нет mem0_id (невозможное состояние)
            FactCreationException: Ошибка внешней системы памяти -> 502
        """
        fact = await self._get_fact_or_404_or_403(fact_id, user_id)

        if not fact.mem0_id:
            raise ValueError(f"Факт {fact.id} не имеет mem0_id - невозможное состояние")

        old_mem0_id = str(fact.mem0_id)

        category = data.category if data.category else FactCategory.PERSONAL

        mem0_metadata = {
            "source_type": FactSource.USER_PROVIDED.value,
            "category": category.value,
        }

        if data.metadata_:
            mem0_metadata.update(data.metadata_)

        try:
            result = await self.memory_service.add(
                messages=data.content,
                user_id=str(user_id),
                infer=False,
                metadata=mem0_metadata,
            )
        except FactCreationException:
            raise
        except Exception as e:
            logger.exception(f"Ошибка mem0ai/Qdrant при обновлении факта {fact_id}")
            raise FactCreationException("Memory service error while updating fact") from e

        try:
            new_mem0_id = result["results"][0]["id"]
        except (KeyError, IndexError, ValueError, TypeError) as e:
            logger.error("mem0ai вернул неожиданный ответ: {!r}", result)
            raise FactCreationException("Memory service returned unexpected response") from e

        update_data = data.model_dump(exclude_unset=True, by_alias=False)
        update_data["mem0_id"] = UUID(str(new_mem0_id))
        update_data["category"] = category

        try:
            await self.fact_repo.update(fact_id, update_data)
        except Exception:
            try:
                await self.memory_service.delete(memory_id=str(new_mem0_id))
            except Exception:
                logger.exception(f"Вектор-сирота {new_mem0_id} остался в Qdrant")
            raise

        try:
            await self.memory_service.delete(memory_id=old_mem0_id)
        except Exception:
            logger.exception(f"Старый вектор {old_mem0_id} не удалён из Qdrant")

        logger.info(f"Факт {fact.id} обновлён с новым mem0_id {new_mem0_id}")

    async def delete_user_fact(
        self,
        fact_id: UUID,
        user_id: UUID,
    ) -> None:
        """
        Удалить факт (мягкое удаление).

        Деактивирует факт в PostgreSQL и удаляет из Qdrant.

        Args:
            fact_id: ID факта для удаления
            user_id: ID пользователя (для проверки владения)

        Raises:
            FactNotFoundException: Если факт не найден или неактивен
            UserProvidedException: Если факт не был создан пользователем
        """

        logger.info(f"Запрос на удаление факта {fact_id} пользователя {user_id}")
        fact = await self._get_fact_or_404_or_403(fact_id, user_id)

        fact.is_active = False
        await self.fact_repo.save(fact)

        if fact.mem0_id:
            await self.memory_service.delete(memory_id=str(fact.mem0_id))

        logger.info(f"Удален факт {fact_id}")

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
           - Создаёт FactModel с данными из Qdrant
        6. Сохраняет все новые факты одним батч-коммитом

        Оптимизация N+1:
        - Вместо 2N запросов использует 2 батч-запроса (messages + existing_facts)
        - Использует set/dict для O(1) поиска вместо запросов в цикле

        Args:
            user_id: UUID пользователя для импорта фактов

        Returns:
            None

        Note:
            - Функция для background task (асинхронная)
            - Пропускает факты с невалидным run_id
            - Категоризирует факты через LLM если нет категории в metadata
        """
        from app.application.prompts.parsing_category import PARSE_CATEGORY
        from app.infrastructure.llms.config import parse_llm_config
        from app.infrastructure.llms.openai import AsyncOpenAILLM

        llm = AsyncOpenAILLM(parse_llm_config)

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
                response = await llm.generate_response(message, response_format={"type": "json_object"})
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

    async def _get_fact_or_404_or_403(self, fact_id: UUID, user_id: UUID) -> Fact:
        """
        Получить факт или выбросить исключение.

        Проверяет что факт существует, активен, принадлежит пользователю
        и является USER_PROVIDED (только такие факты можно редактировать/удалять).

        Args:
            fact_id: UUID факта
            user_id: UUID пользователя

        Returns:
            Fact: Найденный факт

        Raises:
            FactNotFoundException: Если факт не найден или неактивен
            UserProvidedException: Если факт не был создан пользователем (EXTRACTED)
        """
        fact = await self.fact_repo.get_by_id(fact_id=fact_id, user_id=user_id)

        if not fact:
            raise FactNotFoundException(f"Fact {fact_id} not found or not active")

        if fact.source_type != FactSource.USER_PROVIDED:
            raise UserProvidedException(f"Fact {fact_id} not provided")

        return fact

    async def validate_update(self, fact_id: UUID, user_id: UUID) -> None:
        """Проверки 404/403 для обновления факта (вызываются синхронно в роутере)."""
        await self._get_fact_or_404_or_403(fact_id, user_id)
