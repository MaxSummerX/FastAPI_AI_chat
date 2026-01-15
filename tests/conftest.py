"""
Фикстуры для тестирования приложения.

Использует pytest-asyncio для асинхронных тестов и httpx для HTTP запросов.
"""

import asyncio
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models.base_model import Base
from app.models.users import User as UserModel


# Тестовая БД (используем SQLite для скорости)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop]:
    """
    Создаёт event loop для всех тестов.

    Явно создаём loop для стабильности в тестах.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db_engine() -> AsyncGenerator[AsyncEngine]:
    """
    Создаёт тестовый движок БД.

    Использует in-memory SQLite для быстрых тестов.
    Все таблицы создаются перед тестами и удаляются после.
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,  # Выключаем SQL логи в тестах
        future=True,
    )

    # Создаём все таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Удаляем все таблицы после тестов
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """
    Создаёт асинхронную сессию БД для тестов.

    Каждое изменение коммитится и откатывается в конце теста.
    """
    async_session = sessionmaker(
        db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    """
    Создаёт HTTP клиент для тестирования API.

    Подменяет зависимость get_async_postgres_db на тестовую сессию.
    """
    from app.depends.db_depends import get_async_postgres_db

    # Функция-override для зависимости
    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        yield db_session

    # Подменяем зависимость
    app.dependency_overrides[get_async_postgres_db] = override_get_db

    # Создаём клиент с ASGI транспортом
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    # Восстанавливаем оригинальную зависимость
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def test_user(db_session: AsyncSession) -> UserModel:
    """
    Создаёт тестового пользователя в БД.

    Returns:
        UserModel: Созданный пользователь с хешем пароля 'TestPassword123!'
    """
    from app.auth.auth import hash_password

    user = UserModel(
        username="testuser",
        email="test@example.com",
        password_hash=hash_password("TestPassword123!"),
        is_active=True,
        is_verified=True,
    )

    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    return user


@pytest_asyncio.fixture(scope="function")
async def auth_headers(client: AsyncClient, test_user: UserModel) -> dict[str, str]:
    """
    Создаёт JWT токены для аутентификации.

    Returns:
        dict: Заголовки Authorization с Bearer токеном
    """
    # Логинимся и получаем токены
    response = await client.post(
        "/api/v2/user/token",
        data={
            "username": "testuser",
            "password": "TestPassword123!",
        },
    )

    assert response.status_code == 200
    tokens = response.json()

    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest_asyncio.fixture(scope="function")
async def admin_user(db_session: AsyncSession) -> UserModel:
    """
    Создаёт пользователя-администратора для тестов.
    """
    from app.auth.auth import hash_password

    user = UserModel(
        username="admin",
        email="admin@example.com",
        password_hash=hash_password("AdminPassword123!"),
        is_active=True,
        is_verified=True,
    )

    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    return user


@pytest_asyncio.fixture(scope="function")
async def admin_headers(client: AsyncClient, admin_user: UserModel) -> dict[str, str]:
    """
    Создаёт JWT токены для администратора.
    """
    response = await client.post(
        "/api/v2/user/token",
        data={
            "username": "admin",
            "password": "AdminPassword123!",
        },
    )

    assert response.status_code == 200
    tokens = response.json()

    return {"Authorization": f"Bearer {tokens['access_token']}"}
