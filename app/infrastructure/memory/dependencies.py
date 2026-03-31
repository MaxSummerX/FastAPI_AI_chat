"""
Провайдер и фабрика для сервиса памяти (mem0ai).

Управляет жизненным циклом singleton AsyncMemory:
- init_memory() / close_memory() — вызываются из lifespan.py
- get_memory() — возвращает singleton для FastAPI Depends
- create_memory_service() — фабрика для создания IMemoryService
"""

from mem0 import AsyncMemory

from app.domain.services.memory import IMemoryService
from app.infrastructure.memory.config import custom_config
from app.infrastructure.memory.mem0_service import Mem0MemoryService


_memory_service: AsyncMemory | None = None


def init_memory() -> None:
    """
    Инициализирует singleton AsyncMemory. Вызывается из lifespan при старте приложения.
    """
    global _memory_service
    _memory_service = AsyncMemory(config=custom_config)


def close_memory() -> None:
    """
    Закрывает singleton AsyncMemory. Вызывается из lifespan при остановке приложения.
    """
    global _memory_service
    _memory_service = None


def get_memory() -> AsyncMemory:
    """
    Возвращает глобальный singleton AsyncMemory.

    Returns:
        AsyncMemory: Инициализированный инстанс памяти

    Raises:
        RuntimeError: Если память не инициализирована (приложение запущено не через lifespan)
    """
    if _memory_service is None:
        raise RuntimeError("Memory не инициализирован. Запусти приложение через lifespan")
    return _memory_service


def create_memory_service(memory: AsyncMemory) -> IMemoryService:
    """
    Создаёт сервис памяти, реализующий IMemoryService, для application layer.

    Args:
        memory: Инстанс AsyncMemory из mem0ai

    Returns:
        IMemoryService: Сервис памяти для работы с фактами пользователей
    """
    return Mem0MemoryService(memory)
