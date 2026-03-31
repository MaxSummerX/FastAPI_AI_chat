"""
SQLAlchemy реализация репозитория промптов.

Конкретная реализация IPromptRepository для персистентности Prompt сущности
через SQLAlchemy async engine. Следует интерфейсу из domain слоя.
Поддерживает курсорную пагинацию и мягкое удаление (is_active).
"""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.prompt import Prompts as Prompt
from app.domain.repositories.prompts import IPromptRepository
from app.infrastructure.persistence.pagination import paginate_with_cursor


class PromptSQLAlchemyRepository(IPromptRepository):
    """
    SQLAlchemy реализация репозитория промптов.

    Предоставляет CRUD операции для Prompt сущности через SQLAlchemy async.
    Все запросы фильтруют неактивные промпты (is_active=False) по умолчанию.
    Поддерживает мягкое удаление через флаг is_active.
    """

    def __init__(self, db: AsyncSession) -> None:
        """
        Инициализирует репозиторий.

        Args:
            db: Асинхронная сессия SQLAlchemy
        """
        self.db = db

    @staticmethod
    def _base_query(prompt_id: UUID, user_id: UUID) -> Select[tuple[Prompt]]:
        """
        Базовый запрос для получения промпта пользователя.

        Фильтрует по ID, владельцу и исключает неактивные промпты.

        Args:
            prompt_id: Уникальный идентификатор промпта
            user_id: ID пользователя, владельца промпта

        Returns:
            SQLAlchemy Select объект для выполнения запроса
        """
        return select(Prompt).where(
            Prompt.id == prompt_id,
            Prompt.user_id == user_id,
            Prompt.is_active.is_(True),
        )

    async def get_paginated(
        self,
        user_id: UUID,
        cursor: str | None,
        limit: int,
        include_inactive: bool = False,
    ) -> tuple[Sequence[Prompt], str | None, bool]:
        """
        Получить промпты пользователя с курсорной пагинацией.

        Использует индексы (created_at, id) для эффективной пагинации.

        Args:
            user_id: ID пользователя, владельца промптов
            cursor: Курсор из предыдущего ответа для следующей страницы
            limit: Максимальное количество промптов на странице
            include_inactive: Включать ли неактивные промпты в результаты

        Returns:
            Кортеж (промпты, следующий_курсор, есть_ли_следующая_страница)
        """
        conditions = [Prompt.user_id == user_id]

        if not include_inactive:
            conditions.append(Prompt.is_active.is_(True))

        query = select(Prompt).where(*conditions)

        documents, next_cursor, has_next = await paginate_with_cursor(
            db=self.db,
            query=query,
            cursor=cursor,
            limit=limit,
            model=Prompt,
        )

        return documents, next_cursor, has_next

    async def get_by_id(
        self,
        prompt_id: UUID,
        user_id: UUID,
    ) -> Prompt | None:
        """
        Получить промпт по ID.

        Args:
            prompt_id: Уникальный идентификатор промпта
            user_id: ID пользователя, владельца промпта

        Returns:
            Объект Prompt или None если не найден или неактивен
        """
        result: Prompt | None = await self.db.scalar(self._base_query(prompt_id, user_id))
        return result

    async def create(
        self, user_id: UUID, title: str | None, content: str | None, metadata_: dict[str, Any] | None
    ) -> Prompt:
        """
        Создать новый промпт.

        Args:
            user_id: ID пользователя, владельца промпта
            title: Заголовок промпта (опционально)
            content: Содержимое промпта (опционально)
            metadata_: Дополнительные метаданные в формате JSON (опционально)

        Returns:
            Созданный объект Prompt с id и created_at из БД
        """
        prompt = Prompt(
            user_id=user_id,
            title=title,
            content=content,
            metadata_=metadata_,
        )

        self.db.add(prompt)
        await self.db.commit()
        await self.db.refresh(prompt)

        return prompt

    async def delete(self, prompt: Prompt) -> None:
        """
        Удалить промпт.

        Args:
            prompt: Объект Prompt для удаления
        """
        await self.db.delete(prompt)
        await self.db.commit()

    async def save(self, prompt: Prompt) -> Prompt:
        """
        Сохранить изменения промпта.

        Args:
            prompt: Объект Prompt с обновлёнными данными

        Returns:
            Сохранённый объект Prompt
        """
        await self.db.commit()
        await self.db.refresh(prompt)
        return prompt

    async def get_by_id_for_update(self, prompt_id: UUID, user_id: UUID) -> Prompt | None:
        """
        Получить промпт по ID с блокировкой для обновления.

        Использует SELECT ... FOR UPDATE для предотвращения race conditions.

        Args:
            prompt_id: Уникальный идентификатор промпта
            user_id: ID пользователя, владельца промпта

        Returns:
            Объект Prompt или None если не найден или неактивен
        """
        result: Prompt | None = await self.db.scalar(self._base_query(prompt_id, user_id).with_for_update())
        return result
