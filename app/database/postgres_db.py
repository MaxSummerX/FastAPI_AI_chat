from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.utils.env import get_required_env


load_dotenv()

# Строка подключения для PostgreSQl
DATABASE_URL = get_required_env("POSTGRESQL")

# Создаём engine (echo=True, для вывода сообщений в консоль)
async_engine = create_async_engine(DATABASE_URL, echo=True)

# Настраиваем фабрику сеансов
async_session_maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
