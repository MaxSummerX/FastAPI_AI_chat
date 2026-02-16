from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.utils.env import get_required_env


load_dotenv()

# Строка подключения для PostgreSQl
DATABASE_URL = get_required_env("POSTGRESQL")


def create_session_factory() -> async_sessionmaker:
    """Создаёт новый engine и фабрику сессий. Вызывать после fork."""
    engine = create_async_engine(
        DATABASE_URL,
        pool_pre_ping=True,
    )
    return async_sessionmaker(
        engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
