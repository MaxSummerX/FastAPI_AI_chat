"""
Подключение к базе данных.

Модуль предоставляет SQLAlchemy engine и фабрику сессий для асинхронной работы с БД.
Универсальный - поддерживает PostgreSQL, MySQL, SQLite и другие БД через DATABASE_URL.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.infrastructure.settings.settings import settings


DATABASE_URL = settings.DATABASE_URL

# Создаём engine (echo=True, для вывода сообщений в консоль)
async_engine = create_async_engine(DATABASE_URL, echo=True)

# Настраиваем фабрику сеансов
async_session_maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)


def create_session_factory() -> async_sessionmaker:
    """
    Создаёт новый engine и фабрику сессий.

    Использовать после fork процесса для создания изолированных соединений.

    Returns:
        Фабрика сессий async_sessionmaker для создания новых AsyncSession.

    Note:
        Вызывать необходимо после fork процесса, иначе могут возникать
        проблемы с совместным использованием соединений между процессами.
    """
    engine = create_async_engine(
        DATABASE_URL,
        pool_pre_ping=True,
    )
    return async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
