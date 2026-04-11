from uuid import UUID

from loguru import logger

from app.application.exceptions.fact import FactNotFoundException, UserProvidedException
from app.application.schemas.fact import FactBase, FactResponse
from app.application.schemas.pagination import PaginatedResponse
from app.domain.enums.fact import FactCategory, FactSource
from app.domain.models.fact import Fact
from app.infrastructure.memory.mem0_service import IMemoryService
from app.infrastructure.persistence.sqlalchemy.fact_repository import IFactRepository


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
    ) -> PaginatedResponse[FactBase]:
        """
        Получить факты пользователя с курсорной пагинацией.

        Args:
            category: Фильтр по категории фактов (опционально)
            limit: Максимальное количество фактов на странице
            cursor: Курсор из предыдущего ответа для следующей страницы
            source:
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
            items=[FactBase.model_validate(fact) for fact in facts],
            next_cursor=next_cursor,
            has_next=has_next,
        )

    async def get_user_fact_by_id(self, fact_id: UUID, user_id: UUID) -> FactResponse:
        fact = await self.fact_repo.get_by_id(fact_id=fact_id, user_id=user_id)

        if not fact:
            logger.warning("Факт не найден: fact_id={}, user_id={}", fact_id, user_id)
            raise FactNotFoundException(f"Fact {fact_id} not found")

        return FactResponse.model_validate(fact)

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
