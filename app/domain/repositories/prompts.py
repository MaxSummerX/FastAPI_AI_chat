"""
Репозитории промптов.

Интерфейсы для работы с промптами в соответствии с принципами clean architecture.
Определяет контракт для CRUD операций, пагинации и управления неактивными промптами.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from app.domain.models.prompt import Prompts as Prompt


class IPromptRepository(ABC):
    """
    Интерфейс репозитория для работы с промптами.

    Определяет контракт для управления промптами пользователей:
    создание, обновление, удаление (мягкое), пагинация и работа с неактивными промптами.
    """

    @abstractmethod
    async def get_paginated(
        self,
        user_id: UUID,
        cursor: str | None,
        limit: int,
        include_inactive: bool = False,
    ) -> tuple[Sequence[Prompt], str | None, bool]:
        """
        Получить промпты пользователя с курсорной пагинацией.

        Args:
            user_id: ID пользователя, владельца промптов
            cursor: Курсор из предыдущего ответа для следующей страницы
            limit: Максимальное количество промптов на странице
            include_inactive: Включать ли неактивные (удалённые) промпты в результаты

        Returns:
            Кортеж (промпты, следующий_курсор, есть_ли_следующая_страница)
        """
        pass

    @abstractmethod
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
            Объект Prompt или None, если промпт не найден
        """
        pass

    @abstractmethod
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
            Созданный объект Prompt
        """
        pass

    @abstractmethod
    async def delete(self, prompt: Prompt) -> None:
        """
        Удалить промпт (мягкое удаление).

        Аргументы:
            prompt: Объект Prompt для удаления
        """
        pass

    @abstractmethod
    async def save(self, prompt: Prompt) -> Prompt:
        """
        Сохранить изменения промпта.

        Args:
            prompt: Объект Prompt с обновлёнными данными

        Returns:
            Сохранённый объект Prompt
        """
        pass

    @abstractmethod
    async def get_by_id_for_update(self, prompt_id: UUID, user_id: UUID) -> Prompt | None:
        """
        Получить промпт по ID с блокировкой для обновления.

        Используется для предотвращения race conditions при параллельных обновлениях.

        Args:
            prompt_id: Уникальный идентификатор промпта
            user_id: ID пользователя, владельца промпта

        Returns:
            Объект Prompt или None, если промпт не найден
        """
        pass
