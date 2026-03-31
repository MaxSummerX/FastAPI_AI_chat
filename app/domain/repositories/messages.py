"""
Репозитории сообщений (messages).

Интерфейсы для работы с сообщениями в соответствии с принципами clean architecture.
Определяет контракт для CRUD операций и пагинации сообщений в беседах.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from app.domain.models.message import Message


class IMessageRepository(ABC):
    """
    Интерфейс репозитория для работы с сообщениями.

    Определяет контракт для управления сообщениями в беседах:
    создание, получение истории и курсорная пагинация.
    """

    @abstractmethod
    async def create(
        self,
        conversation_id: UUID,
        role: str,
        content: str,
        model: str,
        metadata_: dict | None = None,
    ) -> Message:
        """
        Создать новое сообщение в беседе.

        Args:
            conversation_id: ID беседы, в которой создаётся сообщение
            role: Роль отправителя (user, assistant, system)
            content: Текст сообщения
            model: Название модели, создавшей сообщение (для assistant)
            metadata_: Дополнительные метаданные сообщения

        Returns:
            Созданный объект Message
        """
        pass

    @abstractmethod
    async def get_history(self, conversation_id: UUID, limit: int) -> Sequence[Message]:
        """
        Получить историю сообщений беседы.

        Args:
            conversation_id: ID беседы
            limit: Максимальное количество сообщений

        Returns:
            Последовательность сообщений (от новых к старым)
        """
        pass

    @abstractmethod
    async def get_paginated(
        self,
        conversation_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> tuple[Sequence[Message], str | None, bool]:
        """
        Получить сообщения беседы с курсорной пагинацией.

        Args:
            conversation_id: ID беседы
            cursor: Курсор из предыдущего ответа для следующей страницы
            limit: Максимальное количество сообщений на странице

        Returns:
            Кортеж (сообщения, следующий_курсор, есть_ли_следующая_страница)
        """
        pass
