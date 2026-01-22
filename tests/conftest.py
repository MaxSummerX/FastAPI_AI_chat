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
from app.models import Conversation as ConversationModel
from app.models import Fact as FactModel
from app.models import Message as MessageModel
from app.models.base_model import Base
from app.models.prompts import Prompts as PromptModel
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


# ============================================================
# Фикстуры для Conversations и Messages
# ============================================================


@pytest_asyncio.fixture(scope="function")
async def test_conversation(db_session: AsyncSession, test_user: UserModel) -> ConversationModel:
    """Создаёт тестовую беседу."""
    import uuid

    conversation = ConversationModel(
        id=uuid.uuid4(),
        user_id=test_user.id,
        title="Test Conversation",
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    return conversation


@pytest_asyncio.fixture(scope="function")
async def test_conversations(db_session: AsyncSession, test_user: UserModel) -> list[ConversationModel]:
    """Создаёт несколько тестовых бесед для пагинации."""
    import uuid
    from asyncio import sleep
    from datetime import UTC, datetime

    conversations = []
    # Создаём 25 бесед с разным временем создания
    for i in range(25):
        conv = ConversationModel(
            id=uuid.uuid4(),
            user_id=test_user.id,
            title=f"Conversation {i}",
            created_at=datetime.now(UTC),
        )
        conversations.append(conv)
        db_session.add(conv)
        # Небольшая задержка для разницы во времени
        await sleep(0.001)

    await db_session.commit()

    for conv in conversations:
        await db_session.refresh(conv)

    return conversations


@pytest_asyncio.fixture(scope="function")
async def test_message(db_session: AsyncSession, test_conversation: ConversationModel) -> MessageModel:
    """Создаёт тестовое сообщение."""
    import uuid

    message = MessageModel(
        id=uuid.uuid4(),
        conversation_id=test_conversation.id,
        role="user",
        content="Test message",
        model="gpt-4",
    )
    db_session.add(message)
    await db_session.commit()
    await db_session.refresh(message)

    return message


@pytest_asyncio.fixture(scope="function")
async def test_messages(db_session: AsyncSession, test_conversation: ConversationModel) -> list[MessageModel]:
    """Создаёт несколько тестовых сообщений для пагинации."""
    import uuid
    from asyncio import sleep
    from datetime import UTC, datetime

    messages = []
    # Создаём 50 сообщений
    for i in range(50):
        msg = MessageModel(
            id=uuid.uuid4(),
            conversation_id=test_conversation.id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"Message {i}",
            timestamp=datetime.now(UTC),
            model="gpt-4",
        )
        messages.append(msg)
        db_session.add(msg)
        await sleep(0.001)

    await db_session.commit()

    for msg in messages:
        await db_session.refresh(msg)

    return messages


# ============================================================
# Фикстуры для Facts
# ============================================================


@pytest_asyncio.fixture(scope="function")
async def test_fact(db_session: AsyncSession, test_user: UserModel) -> FactModel:
    """Создаёт тестовый факт."""
    import uuid

    from app.models.facts import FactCategory, FactSource

    fact = FactModel(
        id=uuid.uuid4(),
        user_id=test_user.id,
        content="Test fact about user",
        category=FactCategory.PERSONAL,
        source_type=FactSource.USER_PROVIDED,
        confidence=1.0,
        is_active=True,
    )
    db_session.add(fact)
    await db_session.commit()
    await db_session.refresh(fact)

    return fact


@pytest_asyncio.fixture(scope="function")
async def test_facts(db_session: AsyncSession, test_user: UserModel) -> list[FactModel]:
    """Создаёт несколько тестовых фактов для пагинации."""
    import uuid
    from asyncio import sleep

    from app.models.facts import FactCategory, FactSource

    facts = []
    categories = list(FactCategory)

    # Создаём 30 фактов с разными категориями
    for i in range(30):
        fact = FactModel(
            id=uuid.uuid4(),
            user_id=test_user.id,
            content=f"Test fact number {i}",
            category=categories[i % len(categories)],
            source_type=FactSource.USER_PROVIDED,
            confidence=0.8 + (i % 3) * 0.1,
            is_active=True,
        )
        facts.append(fact)
        db_session.add(fact)
        # Небольшая задержка для разницы во времени
        await sleep(0.001)

    await db_session.commit()

    for fact in facts:
        await db_session.refresh(fact)

    return facts


# ============================================================
# Фикстуры для Prompts
# ============================================================


@pytest_asyncio.fixture(scope="function")
async def test_prompt(db_session: AsyncSession, test_user: UserModel) -> PromptModel:
    """Создаёт тестовый промпт."""
    import uuid
    from datetime import UTC, datetime

    from app.models.prompts import Prompts

    prompt = Prompts(
        id=uuid.uuid4(),
        user_id=test_user.id,
        title="Test Prompt",
        content="You are a helpful assistant",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(prompt)
    await db_session.commit()
    await db_session.refresh(prompt)

    return prompt


@pytest_asyncio.fixture(scope="function")
async def test_prompts(db_session: AsyncSession, test_user: UserModel) -> list[PromptModel]:
    """Создаёт несколько тестовых промптов для пагинации."""
    import uuid
    from asyncio import sleep
    from datetime import UTC, datetime

    from app.models.prompts import Prompts

    prompts = []

    # Создаём 30 промптов с разным временем создания
    for i in range(30):
        prompt = Prompts(
            id=uuid.uuid4(),
            user_id=test_user.id,
            title=f"Prompt {i}",
            content=f"This is prompt content number {i}",
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        prompts.append(prompt)
        db_session.add(prompt)
        await db_session.flush()  # Флаш чтобы получить ID и зафиксировать timestamp
        # Небольшая задержка для разницы во времени
        await sleep(0.001)

    await db_session.commit()

    for prompt in prompts:
        await db_session.refresh(prompt)

    return prompts


# ============================================================
# Фикстуры для Background Tasks (mocking)
# ============================================================


@pytest.fixture(scope="function")
def mock_background_tasks() -> Generator[None]:
    """
    Создаёт мок для BackgroundTasks.

    Используется для тестирования endpoints, которые используют
    фоновые задачи, чтобы избежать их реального выполнения.
    """
    from unittest.mock import patch

    # Патчим функцию конвертации, которая вызывается в background task
    with (
        patch("app.tools.upload.upload_conversations.convert"),
        patch("app.tools.upload.upload_conversations.convert_gtp"),
    ):
        yield


@pytest_asyncio.fixture(scope="function")
async def client_with_mocked_background(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    """
    Создаёт HTTP клиент с замоканными фоновыми задачами.

    Подменяет функции конвертации, которые вызываются в background tasks.
    """
    from unittest.mock import patch

    from app.depends.db_depends import get_async_postgres_db

    # Функция-override для зависимости БД
    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        yield db_session

    # Подменяем зависимости
    app.dependency_overrides[get_async_postgres_db] = override_get_db

    # Создаём клиент с ASGI транспортом и замоканными background функциями
    with (
        patch("app.tools.upload.upload_conversations.convert"),
        patch("app.tools.upload.upload_conversations.convert_gtp"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac

    # Восстанавливаем оригинальные зависимости
    app.dependency_overrides.clear()
