"""
Фикстуры для тестирования приложения.

Использует pytest-asyncio для асинхронных тестов и httpx для HTTP запросов.
"""

import asyncio
from collections.abc import AsyncGenerator, Generator
from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.models import Conversation as ConversationModel
from app.models import Fact as FactModel
from app.models import Invite as InviteModel
from app.models import Message as MessageModel
from app.models import Vacancy as VacancyModel
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
    from app.enum.roles import UserRole

    user = UserModel(
        username="admin",
        email="admin@example.com",
        password_hash=hash_password("AdminPassword123!"),
        is_active=True,
        is_verified=True,
        role=UserRole.ADMIN,
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


@pytest_asyncio.fixture(scope="function")
async def client_with_mocked_import(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    """
    Создаёт HTTP клиент с замоканными функциями импорта вакансий.

    Подменяет функции импорта с hh.ru, которые вызываются в background tasks.
    """
    from unittest.mock import patch

    from app.depends.db_depends import get_async_postgres_db

    # Функция-override для зависимости БД
    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        yield db_session

    # Подменяем зависимости
    app.dependency_overrides[get_async_postgres_db] = override_get_db

    # Создаём асинхронный мок для import_vacancies
    async def mock_import(*args: object, **kwargs: object) -> None:
        """Фейковая функция импорта, которая ничего не делает"""
        pass

    # Патчим функцию импорта в модуле, где она используется (vacancy.py)
    with patch("app.api.v2.vacancy.import_vacancies", side_effect=mock_import):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac

    # Восстанавливаем оригинальные зависимости
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def auth_headers_import(client_with_mocked_import: AsyncClient, test_user: UserModel) -> dict[str, str]:
    """
    Создаёт JWT токены для аутентификации с клиентом, имеющим замоканный импорт.

    Используется для тестов import_vacancies, чтобы избежать реальных HTTP запросов к hh.ru.
    """
    # Логинимся через клиент с замоканным импортом и получаем токены
    response = await client_with_mocked_import.post(
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
async def client_with_mocked_llm(db_session: AsyncSession) -> AsyncGenerator[AsyncClient]:
    """
    Создаёт HTTP клиент с замоканным LLM для тестов vacancy_analysis.

    Подменяет функцию analyze_vacancy_from_db чтобы избежать реальных AI вызовов.
    """
    from unittest.mock import patch

    from app.depends.db_depends import get_async_postgres_db

    # Функция-override для зависимости БД
    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        yield db_session

    # Подменяем зависимости
    app.dependency_overrides[get_async_postgres_db] = override_get_db

    # Создаём асинхронный мок для analyze_vacancy_from_db
    async def mock_analyze(*args: object, **kwargs: object) -> tuple[str, str]:
        """Фейковая функция анализа, которая возвращает тестовые данные"""
        return (
            "Test analysis result",
            "Test prompt template",
        )

    # Патчим функцию анализа в модуле, где она используется (vacancy_analysis.py)
    with patch("app.tools.ai_research.analyze_vacancy_from_db", side_effect=mock_analyze):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac

    # Восстанавливаем оригинальные зависимости
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def auth_headers_llm(client_with_mocked_llm: AsyncClient, test_user: UserModel) -> dict[str, str]:
    """
    Создаёт JWT токены для аутентификации с клиентом, имеющим замоканный LLM.

    Используется для тестов vacancy_analysis, чтобы избежать реальных AI вызовов.
    """
    # Логинимся через клиент с замоканным LLM и получаем токены
    response = await client_with_mocked_llm.post(
        "/api/v2/user/token",
        data={
            "username": "testuser",
            "password": "TestPassword123!",
        },
    )

    assert response.status_code == 200
    tokens = response.json()

    return {"Authorization": f"Bearer {tokens['access_token']}"}


# ============================================================
# Фикстуры для Vacancies
# ============================================================


@pytest_asyncio.fixture(scope="function")
async def test_vacancy(db_session: AsyncSession, test_user: UserModel) -> VacancyModel:
    """Создаёт тестовую вакансию."""
    import uuid
    from datetime import UTC, datetime

    from app.enum.experience import Experience
    from app.models.vacancies import Vacancy

    vacancy = Vacancy(
        id=uuid.uuid4(),
        user_id=test_user.id,
        hh_id="12345678",
        query_request="python developer",
        title="Python Developer",
        description="Test vacancy description",
        salary_from=100000,
        salary_to=150000,
        salary_currency="RUR",
        salary_gross=True,
        experience_id=Experience.tier_1.value,
        area_id="1",
        area_name="Москва",
        schedule_id="fullDay",
        employment_id="full",
        employer_id="12345",
        employer_name="Test Company",
        hh_url="https://hh.ru/vacancy/12345678",
        apply_url="https://hh.ru/vacancy/12345678?apply=true",
        is_active=True,
        is_archived=False,
        is_favorite=False,
        published_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(vacancy)
    await db_session.commit()
    await db_session.refresh(vacancy)

    return vacancy


@pytest_asyncio.fixture(scope="function")
async def test_vacancies(db_session: AsyncSession, test_user: UserModel) -> list[VacancyModel]:
    """Создаёт несколько тестовых вакансий для пагинации."""
    import uuid
    from asyncio import sleep
    from datetime import UTC, datetime, timedelta

    from app.enum.experience import Experience
    from app.models.vacancies import Vacancy

    vacancies = []
    experiences = list(Experience)

    # Создаём 30 вакансий с разным временем создания
    for i in range(30):
        vacancy = Vacancy(
            id=uuid.uuid4(),
            user_id=test_user.id,
            hh_id=f"hh_{i}",
            query_request=f"query_{i % 3}",  # 3 разных запроса
            title=f"Vacancy {i}",
            description=f"Description for vacancy {i}",
            salary_from=50000 + i * 1000,
            salary_to=80000 + i * 1000,
            salary_currency="RUR",
            salary_gross=True,
            experience_id=experiences[i % len(experiences)].value,
            area_id=str(i % 5),
            area_name=f"City {i % 5}",
            schedule_id="fullDay" if i % 2 == 0 else "remote",
            employment_id="full",
            employer_id=f"employer_{i % 5}",
            employer_name=f"Company {i % 5}",
            hh_url=f"https://hh.ru/vacancy/{i}",
            apply_url=f"https://hh.ru/vacancy/{i}?apply=true",
            is_active=True,
            is_archived=i % 10 == 0,  # Каждая 10-я архивная
            is_favorite=i % 5 == 0,  # Каждая 5-я в избранном
            published_at=datetime.now(UTC) - timedelta(days=i),
            created_at=datetime.now(UTC) - timedelta(seconds=i * 0.1),
            updated_at=datetime.now(UTC) - timedelta(seconds=i * 0.1),
        )
        vacancies.append(vacancy)
        db_session.add(vacancy)
        await db_session.flush()
        # Небольшая задержка для разницы во времени
        await sleep(0.001)

    await db_session.commit()

    for vacancy in vacancies:
        await db_session.refresh(vacancy)

    return vacancies


# ============================================================
# Фикстуры для VacancyAnalysis
# ============================================================


@pytest_asyncio.fixture(scope="function")
async def test_vacancy_analysis(
    db_session: AsyncSession, test_user: UserModel, test_vacancy: VacancyModel
) -> VacancyModel:
    """Создаёт тестовый анализ вакансии."""
    import uuid
    from datetime import UTC, datetime

    from app.enum.analysis import AnalysisType
    from app.models.vacancy_analysis import VacancyAnalysis

    analysis = VacancyAnalysis(
        id=uuid.uuid4(),
        vacancy_id=test_vacancy.id,
        user_id=test_user.id,
        title="Соответствие вакансии",
        analysis_type=AnalysisType.MATCHING.value,
        prompt_template="Test prompt template",
        custom_prompt=None,
        result_data={"score": 85, "match": "high"},
        result_text="Test analysis result",
        model_used="gpt-4",
        tokens_used=1000,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(analysis)
    await db_session.commit()
    await db_session.refresh(analysis)

    return analysis


@pytest_asyncio.fixture(scope="function")
async def test_vacancy_analyses(
    db_session: AsyncSession, test_user: UserModel, test_vacancy: VacancyModel
) -> list[VacancyModel]:
    """Создаёт несколько тестовых анализов вакансии."""
    import uuid
    from asyncio import sleep
    from datetime import UTC, datetime

    from app.enum.analysis import AnalysisType
    from app.models.vacancy_analysis import VacancyAnalysis

    analyses = []
    # Создаём анализы разных типов
    for i, analysis_type in enumerate(AnalysisType):
        analysis = VacancyAnalysis(
            id=uuid.uuid4(),
            vacancy_id=test_vacancy.id,
            user_id=test_user.id,
            title=analysis_type.display_name,
            analysis_type=analysis_type.value,
            prompt_template=f"Template for {analysis_type.value}",
            custom_prompt="Custom prompt" if analysis_type == AnalysisType.CUSTOM else None,
            result_data={"index": i},
            result_text=f"Analysis result {i}",
            model_used="gpt-4",
            tokens_used=500 + i * 100,
            created_at=datetime.now(UTC) - timedelta(seconds=i * 0.1),
            updated_at=datetime.now(UTC) - timedelta(seconds=i * 0.1),
        )
        analyses.append(analysis)
        db_session.add(analysis)
        await db_session.flush()
        await sleep(0.001)

    await db_session.commit()

    for analysis in analyses:
        await db_session.refresh(analysis)

    return analyses


# ============================================================
# Фикстуры для Invites
# ============================================================


@pytest_asyncio.fixture(scope="function")
async def test_invite(db_session: AsyncSession) -> InviteModel:
    """Создаёт тестовый инвайт-код."""
    import uuid
    from datetime import UTC, datetime

    from app.models.invites import Invite

    invite = Invite(
        id=uuid.uuid4(),
        code="test_invite_code_123456789",
        is_used=False,
        used_by_user_id=None,
        created_at=datetime.now(UTC),
        used_at=None,
    )
    db_session.add(invite)
    await db_session.commit()
    await db_session.refresh(invite)

    return invite


@pytest_asyncio.fixture(scope="function")
async def test_invites(db_session: AsyncSession, test_user: UserModel, admin_user: UserModel) -> list[InviteModel]:
    """Создаёт несколько тестовых инвайт-кодов."""
    import uuid
    from datetime import UTC, datetime, timedelta

    from app.models.invites import Invite

    invites = []

    # Создаём 10 инвайт-кодов
    for i in range(10):
        is_used = i < 3  # Первые 3 использованы
        invite = Invite(
            id=uuid.uuid4(),
            code=f"invite_code_{i:02d}_123456789",
            is_used=is_used,
            used_by_user_id=test_user.id if is_used else None,
            created_at=datetime.now(UTC) - timedelta(days=i),
            used_at=datetime.now(UTC) - timedelta(days=i) if is_used else None,
        )
        invites.append(invite)
        db_session.add(invite)
        await db_session.flush()

    await db_session.commit()

    for invite in invites:
        await db_session.refresh(invite)

    return invites
