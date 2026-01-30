"""
Управление жизненным циклом FastAPI приложения.

Модуль содержит lifespan функцию для корректной инициализации
и освобождения ресурсов при старте и остановке приложения.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Управление жизненным циклом FastAPI приложения.

    Startup: инициализация ресурсов
    - Инициализация HTTP клиентов для hh.ru
    - Прогрев соединений

    Shutdown: корректное закрытие ресурсов
    - Закрытие HTTP клиентов

    Args:
        app: Экземпляр FastAPI приложения

    Yields:
        None: Контекстный менеджер для использования в FastAPI
    """

    logger.info("🚀 FastAPI application starting up...")

    from app.tools.headhunter.headhunter_client import close_hh_client, get_hh_client, warmup_hh_client

    logger.info("🔌 Initializing HTTP clients...")
    await get_hh_client()  # Создаём клиент
    await warmup_hh_client()  # Прогреваем соединение
    logger.info("✅ HTTP clients ready")

    yield

    # ============================================================
    # SHUTDOWN - Освобождение ресурсов
    # ============================================================
    logger.info("🛑 FastAPI application shutting down...")
    await close_hh_client()
    logger.info("✅ HTTP clients closed successfully")
