"""
Зависимости базы данных для FastAPI.

Модуль предоставляет dependency-функции для внедрения сессий БД в FastAPI эндпоинты
согласно принципам Dependency Injection и чистой архитектуры.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.connection import async_session_maker


async def get_db() -> AsyncGenerator[AsyncSession]:
    """
    Dependency-функция для получения асинхронной сессии БД в FastAPI эндпоинтах.

    Используется с FastAPI Depends() для автоматического управления сессией:
    - Создаёт сессию при вызове эндпоинта
    - Автоматически закрывает после выполнения запроса

    Yields:
        AsyncSession: Асинхронная сессия SQLAlchemy для работы с БД.
    """
    async with async_session_maker() as session:
        yield session
