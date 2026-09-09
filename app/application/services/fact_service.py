from uuid import UUID

from loguru import logger

from app.application.exceptions.fact import FactCreationException, FactNotFoundException, UserProvidedException
from app.application.schemas.fact import FactCreate, FactResponse
from app.application.schemas.pagination import PaginatedResponse
from app.domain.enums.fact import FactCategory, FactSource
from app.domain.models.fact import Fact
from app.domain.repositories.facts import IFactRepository
from app.domain.services.memory import IMemoryService


class FactService:
    """Сервис для управления фактами пользователей."""

    def __init__(self, fact_repo: IFactRepository, memory_service: IMemoryService) -> None:
        self.fact_repo = fact_repo
        self.memory_service = memory_service

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
