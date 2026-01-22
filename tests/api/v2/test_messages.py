"""
Тесты для message endpoints API v2.

Покрывает все основные сценарии:
- Получение сообщений с курсорной пагинацией
- Добавление сообщений
- Стриминг ответов
- Обработка ошибок
"""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation as ConversationModel
from app.models import Message as MessageModel
from app.models import User as UserModel


# ============================================================
# GET /conversations/{id}/messages - курсорная пагинация
# ============================================================


@pytest.mark.asyncio
async def test_get_messages_unauthorized(client: AsyncClient, test_conversation: ConversationModel) -> None:
    """Тест: неавторизованный запрос к messages"""
    response = await client.get(f"/api/v2/conversations/{test_conversation.id}/messages")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_messages_conversation_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: запрос сообщений несуществующей беседы"""
    import uuid

    response = await client.get(f"/api/v2/conversations/{uuid.uuid4()}/messages", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_messages_first_load(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_messages: list[MessageModel],
    test_conversation: ConversationModel,
) -> None:
    """Тест: первая загрузка сообщений (без cursor)"""
    response = await client.get(
        f"/api/v2/conversations/{test_conversation.id}/messages", headers=auth_headers, params={"limit": 20}
    )
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert "next_cursor" in data
    assert "has_next" in data

    # Должно вернуть 20 сообщений
    assert len(data["items"]) == 20
    # Есть ещё более старые сообщения (всего 50, загрузили 20)
    assert data["has_next"] is True
    # Курсор должен быть для следующей страницы
    assert data["next_cursor"] is not None


@pytest.mark.asyncio
async def test_get_messages_with_cursor(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_messages: list[MessageModel],
    test_conversation: ConversationModel,
) -> None:
    """Тест: загрузка более старых сообщений (cursor)"""
    # Первая загрузка
    first_response = await client.get(
        f"/api/v2/conversations/{test_conversation.id}/messages", headers=auth_headers, params={"limit": 20}
    )
    first_data = first_response.json()
    cursor = first_data["next_cursor"]

    # Загружаем более старые
    response = await client.get(
        f"/api/v2/conversations/{test_conversation.id}/messages",
        headers=auth_headers,
        params={"limit": 10, "cursor": cursor},
    )
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) == 10
    assert data["has_next"] is True  # Ещё есть старые (всего 50, 20+10=30)


@pytest.mark.asyncio
async def test_get_messages_pagination_to_end(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_messages: list[MessageModel],
    test_conversation: ConversationModel,
) -> None:
    """Тест: пагинация до конца (все сообщения загружены)"""
    # Загружаем все сообщения порциями
    all_items = []
    cursor = None

    for _ in range(10):  # Макс 10 итераций
        params = {"limit": 10}
        if cursor:
            params["cursor"] = cursor

        response = await client.get(
            f"/api/v2/conversations/{test_conversation.id}/messages", headers=auth_headers, params=params
        )
        data = response.json()

        all_items.extend(data["items"])

        if not data["has_next"]:
            break

        cursor = data["next_cursor"]

    # Должны загрузить все 50 сообщений
    assert len(all_items) == 50


@pytest.mark.asyncio
async def test_get_messages_invalid_cursor(
    client: AsyncClient, auth_headers: dict[str, str], test_conversation: ConversationModel
) -> None:
    """Тест: использование невалидного курсора"""
    response = await client.get(
        f"/api/v2/conversations/{test_conversation.id}/messages",
        headers=auth_headers,
        params={"cursor": "invalid_cursor_base64"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_messages_ordering_desc(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_messages: list[MessageModel],
    test_conversation: ConversationModel,
) -> None:
    """Тест: проверка правильности сортировки (от нового к старому)"""
    response = await client.get(
        f"/api/v2/conversations/{test_conversation.id}/messages", headers=auth_headers, params={"limit": 10}
    )
    assert response.status_code == 200

    data = response.json()
    items = data["items"]

    # Проверяем что сообщения упорядочены от НОВОГО к СТАРОМУ (DESC)
    # Фронтенд сам развернёт как нужно
    for i in range(len(items) - 1):
        current_timestamp = items[i]["timestamp"]
        next_timestamp = items[i + 1]["timestamp"]
        # Для DESC порядок: текущий >= следующего
        assert current_timestamp >= next_timestamp


@pytest.mark.asyncio
async def test_get_messages_empty_conversation(
    client: AsyncClient, auth_headers: dict[str, str], test_conversation: ConversationModel
) -> None:
    """Тест: получение сообщений из пустой беседы"""
    response = await client.get(f"/api/v2/conversations/{test_conversation.id}/messages", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) == 0
    assert data["has_next"] is False
    assert data["next_cursor"] is None


@pytest.mark.asyncio
async def test_get_messages_limit_validation(
    client: AsyncClient, auth_headers: dict[str, str], test_conversation: ConversationModel
) -> None:
    """Тест: валидация limit параметра"""
    # Слишком большой limit
    response = await client.get(
        f"/api/v2/conversations/{test_conversation.id}/messages", headers=auth_headers, params={"limit": 150}
    )
    # Должен использовать максимальное значение (100)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_messages_limit_minimum(
    client: AsyncClient, auth_headers: dict[str, str], test_conversation: ConversationModel
) -> None:
    """Тест: limit меньше минимума возвращает ошибку валидации"""
    response = await client.get(
        f"/api/v2/conversations/{test_conversation.id}/messages", headers=auth_headers, params={"limit": 0}
    )
    # Query validation в FastAPI возвращает 422 для невалидных значений
    assert response.status_code == 422


# ============================================================
# POST /conversations/{id}/messages - добавление сообщения
# ============================================================


@pytest.mark.asyncio
async def test_add_message_unauthorized(client: AsyncClient, test_conversation: ConversationModel) -> None:
    """Тест: добавление сообщения без авторизации"""
    response = await client.post(
        f"/api/v2/conversations/{test_conversation.id}/messages", json={"role": "user", "content": "Test message"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_add_message_conversation_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: добавление сообщения в несуществующую беседу"""
    import uuid

    response = await client.post(
        f"/api/v2/conversations/{uuid.uuid4()}/messages",
        headers=auth_headers,
        json={"role": "user", "content": "Test message"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_add_message_success(
    client: AsyncClient, auth_headers: dict[str, str], test_conversation: ConversationModel, mocker: Any
) -> None:
    """Тест: успешное добавление сообщения (мок LLM)"""

    # Мокаем LLM чтобы не делать реальный запрос
    async def mock_generate_response(
        self: Any,
        messages: list,
        response_format: str | None = None,
        tools: list | None = None,
        tool_choice: str = "auto",
        **kwargs: Any,
    ) -> str:
        return "Mock AI response"

    mocker.patch("app.llms.openai.AsyncOpenAILLM.generate_response", mock_generate_response)

    response = await client.post(
        f"/api/v2/conversations/{test_conversation.id}/messages",
        headers=auth_headers,
        json={"role": "user", "content": "Hello, how are you?"},
    )
    assert response.status_code == 201

    data = response.json()
    assert "id" in data
    assert data["role"] == "assistant"
    assert "content" in data


@pytest.mark.asyncio
async def test_add_message_with_custom_prompt(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_conversation: ConversationModel,
    db_session: AsyncSession,
    test_user: UserModel,
    mocker: Any,
) -> None:
    """Тест: добавление сообщения с кастомным промптом"""
    # Создаём кастомный промпт
    import uuid

    from app.models.prompts import Prompts

    prompt = Prompts(
        id=uuid.uuid4(),
        user_id=test_user.id,
        title="Custom Prompt",
        content="You are a helpful assistant.",
        is_active=True,
    )
    db_session.add(prompt)
    await db_session.commit()

    # Мокаем LLM
    async def mock_generate_response(
        self: Any,
        messages: list,
        response_format: str | None = None,
        tools: list | None = None,
        tool_choice: str = "auto",
        **kwargs: Any,
    ) -> str:
        return "Custom prompt response"

    mocker.patch("app.llms.openai.AsyncOpenAILLM.generate_response", mock_generate_response)

    response = await client.post(
        f"/api/v2/conversations/{test_conversation.id}/messages?prompt_id={prompt.id}",
        headers=auth_headers,
        json={"role": "user", "content": "Test"},
    )
    assert response.status_code == 201

    data = response.json()
    assert "id" in data
    assert data["role"] == "assistant"


@pytest.mark.asyncio
async def test_add_message_validation_error(
    client: AsyncClient, auth_headers: dict[str, str], test_conversation: ConversationModel
) -> None:
    """Тест: добавление сообщения с невалидными данными"""
    response = await client.post(
        f"/api/v2/conversations/{test_conversation.id}/messages",
        headers=auth_headers,
        json={
            "role": "user",
            "content": "",  # Пустой контент
        },
    )
    # Должна быть валидация Pydantic
    assert response.status_code == 422


# ============================================================
# POST /conversations/{id}/messages/stream - стриминг
# ============================================================


@pytest.mark.asyncio
async def test_stream_message_unauthorized(client: AsyncClient, test_conversation: ConversationModel) -> None:
    """Тест: стриминг без авторизации"""
    response = await client.post(
        f"/api/v2/conversations/{test_conversation.id}/messages/stream",
        json={"role": "user", "content": "Test message"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_stream_message_conversation_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: стриминг в несуществующую беседу"""
    import uuid

    response = await client.post(
        f"/api/v2/conversations/{uuid.uuid4()}/messages/stream",
        headers=auth_headers,
        json={"role": "user", "content": "Test"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_stream_message_archived_conversation(
    client: AsyncClient, auth_headers: dict[str, str], test_conversation: ConversationModel, db_session: AsyncSession
) -> None:
    """Тест: стриминг в архивированную беседу"""
    # Архивируем беседу
    test_conversation.is_archived = True
    await db_session.commit()

    response = await client.post(
        f"/api/v2/conversations/{test_conversation.id}/messages/stream",
        headers=auth_headers,
        json={"role": "user", "content": "Test"},
    )
    # Должен вернуть 404 (archived conversations filtered)
    assert response.status_code == 404


# ============================================================
# POST /conversations/{id}/messages/stream_v2 - улучшенный стриминг
# ============================================================


@pytest.mark.asyncio
async def test_stream_v2_message_empty_content(
    client: AsyncClient, auth_headers: dict[str, str], test_conversation: ConversationModel
) -> None:
    """Тест: stream_v2 с пустым контентом"""
    response = await client.post(
        f"/api/v2/conversations/{test_conversation.id}/messages/stream_v2",
        headers=auth_headers,
        json={
            "role": "user",
            "content": "",  # Пустой
        },
    )
    # Pydantic валидация возвращает 422 для пустого контента
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_stream_v2_invalid_conversation_id(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: stream_v2 с невалидным conversation_id"""
    response = await client.post(
        "/api/v2/conversations/00000000-0000-0000-0000-000000000000/messages/stream_v2",
        headers=auth_headers,
        json={"role": "user", "content": "Test"},
    )
    assert response.status_code == 404


# ============================================================
# Проверка доступа к чужим сообщениям
# ============================================================


@pytest.mark.asyncio
async def test_get_messages_other_user_conversation(
    client: AsyncClient, admin_headers: dict[str, str], test_conversation: ConversationModel
) -> None:
    """Тест: попытка получить сообщения из чужой беседы"""
    response = await client.get(f"/api/v2/conversations/{test_conversation.id}/messages", headers=admin_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_add_message_to_other_user_conversation(
    client: AsyncClient, admin_headers: dict[str, str], test_conversation: ConversationModel
) -> None:
    """Тест: попытка добавить сообщение в чужую беседу"""
    response = await client.post(
        f"/api/v2/conversations/{test_conversation.id}/messages",
        headers=admin_headers,
        json={"role": "user", "content": "Hack!"},
    )
    assert response.status_code == 404
