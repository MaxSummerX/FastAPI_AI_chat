"""
Mem0 реализация сервиса памяти для infrastructure layer.

Адаптер над AsyncMemory (mem0ai), реализующий интерфейс IMemoryService
для использования в application layer. Обеспечивает хранение,
поиск и управление фактами о пользователях через векторную БД.
"""

from typing import Any

from mem0 import AsyncMemory

from app.domain.services.memory import IMemoryService


class Mem0MemoryService(IMemoryService):
    """
    Mem0 сервис памяти.

    Адаптер над AsyncMemory (mem0ai) для использования в application layer.
    Реализует интерфейс IMemoryService, инкапсулируя работу с mem0ai:
    векторное хранилище (Qdrant), графовые связи (Neo4j), эмбеддинги (Ollama).
    """

    def __init__(self, memory: AsyncMemory) -> None:
        """
        Инициализирует сервис памяти.

        Args:
            memory: Инстанс AsyncMemory из mem0ai (singleton из provider)
        """
        self._memory = memory

    async def add(
        self,
        messages: list[dict[str, str]],
        user_id: str,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Добавить новые факты в память пользователя.

        Извлекает факты из сообщений и сохраняет в векторное хранилище.

        Args:
            messages: Сообщения для извлечения фактов
            user_id: Идентификатор пользователя
            run_id: Опциональный ID запуска (для группировки)
            metadata: Дополнительные метаданные (source_type, и т.д.)

        Returns:
            Результат операции с добавленными фактами
        """
        result: dict[str, Any] = await self._memory.add(
            messages=messages,
            user_id=user_id,
            run_id=run_id,
            metadata=metadata or {},
        )
        return result

    async def search(
        self,
        query: str,
        user_id: str,
        limit: int = 100,
        threshold: float = 0.0,
    ) -> dict[str, Any]:
        """
        Найти релевантные факты по запросу.

        Выполняет семантический поиск по векторному хранилищу.

        Args:
            query: Поисковый запрос
            user_id: Идентификатор пользователя
            limit: Максимальное количество результатов
            threshold: Минимальный порог схожести (0.0-1.0)

        Returns:
            Результаты поиска: {"results": [{"id": "...", "memory": "...", "score": 0.95}]}
        """
        result: dict[str, Any] = await self._memory.search(
            query=query,
            user_id=user_id,
            limit=limit,
            threshold=threshold,
        )
        return result

    async def get_all(
        self,
        user_id: str,
        limit: int = 100,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Получить все факты пользователя.

        Args:
            user_id: Идентификатор пользователя
            limit: Максимальное количество результатов
            filters: Дополнительные фильтры для запроса

        Returns:
            Все факты: {"results": [...], "relations": [...]}
        """
        result: dict[str, Any] = await self._memory.get_all(user_id=user_id, filters=filters)
        return result

    async def delete(self, memory_id: str) -> dict[str, str]:
        """
        Удалить конкретный факт из памяти.

        Args:
            memory_id: Идентификатор факта для удаления

        Returns:
            Результат операции: {"message": "Memory deleted successfully!"}
        """
        result: dict[str, str] = await self._memory.delete(memory_id=memory_id)
        return result

    async def delete_all(self, user_id: str) -> dict[str, str]:
        """
        Удалить все факты пользователя.

        Args:
            user_id: Идентификатор пользователя

        Returns:
            Результат операции удаления
        """
        result: dict[str, str] = await self._memory.delete_all(user_id=user_id)
        return result
