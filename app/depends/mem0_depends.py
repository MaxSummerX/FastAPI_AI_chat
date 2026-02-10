from mem0 import AsyncMemory

from app.configs.memory import custom_config


_memory_service: AsyncMemory | None = None


def init_memory() -> None:
    """Инициализирует singleton AsyncMemory. Вызывается из lifespan."""
    global _memory_service
    _memory_service = AsyncMemory(config=custom_config)


def close_memory() -> None:
    """Закрывает singleton AsyncMemory. Вызывается из lifespan."""
    global _memory_service
    _memory_service = None


def get_memory() -> AsyncMemory:
    """Возвращает глобальный singleton."""
    if _memory_service is None:
        raise RuntimeError("Memory не инициализирован. Запусти приложение через lifespan")
    return _memory_service
