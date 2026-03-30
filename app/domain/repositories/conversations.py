"""
Репозитории бесед (conversations).

Интерфейсы для работы с беседами в соответствии с принципами clean architecture.
Определяет контракт для CRUD операций, пагинации и управления импортированными беседами.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from app.domain.models.conversation import Conversation


class IConversationRepository(ABC):
    """
    Интерфейс репозитория для работы с беседами.

    Определяет контракт для управления беседами пользователей:
    создание, обновление, удаление, пагинация и работа с импортированными беседами.
    """

    @abstractmethod
    async def get_paginated(
        self,
        user_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> tuple[Sequence[Conversation], str | None, bool]:
        """
        Получить беседы пользователя с курсорной пагинацией.

        Args:
            user_id: ID пользователя, владельца бесед
            cursor: Курсор из предыдущего ответа для следующей страницы
            limit: Максимальное количество бесед на странице

        Returns:
            Кортеж (беседы, следующий_курсор, есть_ли_следующая_страница)
        """
        pass

    @abstractmethod
    async def get_by_id(
        self,
        conversation_id: UUID,
        user_id: UUID,
    ) -> Conversation | None:
        """
        Получить беседу по ID.

        Args:
            conversation_id: Уникальный идентификатор беседы
            user_id: ID пользователя, владельца беседы

        Returns:
            Объект Conversation или None, если беседа не найдена
        """
        pass

    @abstractmethod
    async def create(
        self,
        user_id: UUID,
        title: str | None,
    ) -> Conversation:
        """
        Создать новую беседу.

        Args:
            user_id: ID пользователя, владельца беседы
            title: Название беседы (опционально)

        Returns:
            Созданный объект Conversation
        """
        pass

    @abstractmethod
    async def create_from_import(
        self,
        user_id: UUID,
        title: str | None,
        source: str | None = None,
        source_id: UUID | None = None,
        is_imported: bool = True,
    ) -> Conversation:
        """
        Создать беседу из импортированных данных.

        Используется при импорте диалогов из внешних источников
        (Claude.ai, ChatGPT и др.).

        Args:
            user_id: ID пользователя, владельца беседы
            title: Название беседы
            source: Источник импорта (например, "claude", "gpt")
            source_id: ID беседы в источнике импорта
            is_imported: Флаг, помечающий беседу как импортированную

        Returns:
            Созданный объект Conversation
        """
        pass

    @abstractmethod
    async def delete(self, conversation: Conversation) -> None:
        """
        Удалить беседу.

        Args:
            conversation: Объект Conversation для удаления
        """
        pass

    @abstractmethod
    async def save(self, conversation: Conversation) -> Conversation:
        """
        Сохранить изменения беседы.

        Args:
            conversation: Объект Conversation с обновлёнными данными

        Returns:
            Сохранённый объект Conversation
        """
        pass

    @abstractmethod
    async def get_by_id_for_update(self, conversation_id: UUID, user_id: UUID) -> Conversation | None:
        """
        Получить беседу по ID с блокировкой для обновления.

        Используется для предотвращения race conditions при параллельных обновлениях.
        Применяет SELECT FOR UPDATE для блокировки записи на время транзакции.

        Args:
            conversation_id: Уникальный идентификатор беседы
            user_id: ID пользователя, владельца беседы

        Returns:
            Объект Conversation или None, если беседа не найдена
        """
        pass
