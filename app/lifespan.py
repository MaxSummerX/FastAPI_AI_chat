"""
Управление жизненным циклом FastAPI приложения.

Модуль содержит lifespan функцию для корректной инициализации
и освобождения ресурсов при старте и остановке приложения.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from app.depends.mem0_depends import close_memory, init_memory
from app.tools.headhunter.headhunter_client import close_hh_client, get_hh_client, warmup_hh_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Управление жизненным циклом FastAPI приложения.

    Startup (запуск):
        - Инициализация singleton AsyncMemory (система памяти)
        - Создание и прогрев HTTP клиента для hh.ru

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

    logger.info("🔌 Инициализация HTTP клиента...")
    await get_hh_client()  # Создаём клиент
    await warmup_hh_client()  # Прогреваем соединение
    logger.info("✅ HTTP клиенты готовы")

    yield

    logger.info("🛑 Остановка FastAPI приложения...")
    await close_hh_client()
    logger.info("✅ HTTP клиенты закрыты")
    logger.info("🛑 Закрытие AsyncMemory")
    close_memory()
