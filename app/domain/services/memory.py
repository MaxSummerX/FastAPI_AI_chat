"""Интерфейсы сервисов памяти для доменного слоя.

Определяет контракт для управления долгосрочной памятью пользователя
(фактами, контекстом) через абстракции, не зависящие от конкретных реализаций.
"""

from abc import ABC, abstractmethod
from typing import Any


class IMemoryService(ABC):
    """Интерфейс сервиса для работы с памятью.

    Определяет контракт для хранения, поиска и управления фактами
    о пользователях. Используется для персонализации AI-ответов.
    """

    @abstractmethod
    async def add(
        self,
        messages: list[dict[str, str]],
        user_id: str,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Добавить новые факты в память пользователя.

        Args:
            messages: Сообщения для извлечения фактов
            user_id: Идентификатор пользователя
            run_id: Опциональный ID запуска (для группировки)
            metadata: Дополнительные метаданные для хранения

        Returns:
            Результат операции с добавленными фактами
        """

    @abstractmethod
    async def search(
        self,
        query: str,
        user_id: str,
        limit: int = 100,
        threshold: float = 0.0,
    ) -> dict[str, Any]:
        """Найти релевантные факты по запросу.

        Args:
            query: Поисковый запрос
            user_id: Идентификатор пользователя
            limit: Максимальное количество результатов
            threshold: Минимальный порог схожести (0.0-1.0)

        Returns:
            Результаты поиска с релевантными фактами
        """

    @abstractmethod
    async def get_all(self, user_id: str, limit: int = 100) -> dict[str, Any]:
        """Получить все факты пользователя.

        Args:
            user_id: Идентификатор пользователя
            limit: Максимальное количество результатов

        Returns:
            Все факты пользователя с метаданными
        """

    @abstractmethod
    async def delete(self, memory_id: str) -> dict[str, Any]:
        """Удалить конкретный факт из памяти.

        Args:
            memory_id: Идентификатор факта для удаления

        Returns:
            Результат операции удаления
        """

    @abstractmethod
    async def delete_all(self, user_id: str) -> dict[str, Any]:
        """Удалить все факты пользователя.

        Args:
            user_id: Идентификатор пользователя

        Returns:
            Результат операции удаления
        """
