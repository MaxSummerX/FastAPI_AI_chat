import gc
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mem0 import AsyncMemory

from app.configs.memory import custom_config


@asynccontextmanager
async def get_memory() -> AsyncIterator[AsyncMemory]:
    """Асинхронный менеджер контекста для экземпляра mem0."""
    memory: AsyncMemory = AsyncMemory(config=custom_config)
    try:
        yield memory
    finally:
        gc.collect()
