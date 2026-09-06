"""
Управление жизненным циклом FastAPI приложения.

Модуль содержит lifespan функцию для корректной инициализации
и освобождения ресурсов при старте и остановке приложения.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from app.infrastructure.cache.redis import ping_redis, redis_async
from app.infrastructure.hh.headhunter_client import close_hh_client, get_hh_client
from app.infrastructure.memory.dependencies import close_memory, init_memory


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Управление жизненным циклом FastAPI приложения.

    Startup (запуск):
        - Инициализация singleton AsyncMemory (система памяти)
        - Создание HTTP клиента для hh.ru

    Shutdown (остановка):
        - Закрытие HTTP клиента
        - Очистка singleton AsyncMemory

    Args:
        app: Экземпляр FastAPI приложения

    Yields:
        None: Контекстный менеджер для использования в FastAPI
    """

    logger.info("🚀 Запуск FastAPI приложения...")
    logger.info("🚀 Инициализация AsyncMemory")
    init_memory()
    if await ping_redis():
        logger.info("✅ Redis (замки) доступен")
    else:
        logger.warning("⚠️ Redis недоступен.")
    logger.info("🔌 Инициализация HTTP клиента...")
    await get_hh_client()  # Создаём клиент
    logger.info("✅ HTTP клиенты готовы")

    yield

    logger.info("🛑 Остановка FastAPI приложения...")

    try:
        logger.info("🛑 Закрытие hh_client")
        await close_hh_client()
    except Exception as e:
        logger.error("Ошибка при закрытии hh-клиента: {}", e)

    try:
        logger.info("🛑 Закрытие Redis")
        await redis_async.aclose()
    except Exception as e:
        logger.error("Ошибка при закрытии Redis: {}", e)

    try:
        logger.info("🛑 Закрытие AsyncMemory")
        close_memory()
    except Exception as e:
        logger.error("Ошибка при закрытии AsyncMemory: {}", e)
