"""
Тесты для conversation endpoints API v2.

Покрывает все основные сценарии:
- Получение бесед с пагинацией
- Создание новой беседы
- Обновление беседы
- Удаление беседы
- Обработка ошибок
"""

import pytest
from httpx import AsyncClient

from app.models import Conversation as ConversationModel


# ============================================================
# GET /conversations - получение бесед с пагинацией
# ============================================================


@pytest.mark.asyncio
async def test_get_conversations_unauthorized(client: AsyncClient) -> None:
    """Тест: неавторизованный запрос к /conversations"""
    response = await client.get("/api/v2/conversations/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_conversations_first_page(
    client: AsyncClient, auth_headers: dict[str, str], test_conversations: list
) -> None:
    """Тест: получение первой страницы бесед (без курсора)"""
    response = await client.get("/api/v2/conversations/", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert "next_cursor" in data
    assert "has_next" in data

    # Должно вернуть 20 бесед (default limit)
    assert len(data["items"]) == 20
    assert data["has_next"] is True  # Ещё есть 5 бесед
    assert data["next_cursor"] is not None


@pytest.mark.asyncio
async def test_get_conversations_with_custom_limit(
    client: AsyncClient, auth_headers: dict[str, str], test_conversations: list
) -> None:
    """Тест: получение бесед с кастомным limit"""
    response = await client.get("/api/v2/conversations/", headers=auth_headers, params={"limit": 10})
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) == 10
    assert data["has_next"] is True


@pytest.mark.asyncio
async def test_get_conversations_with_cursor(
    client: AsyncClient, auth_headers: dict[str, str], test_conversations: list
) -> None:
    """Тест: получение второй страницы с курсором"""
    # Первая страница
    first_response = await client.get("/api/v2/conversations/", headers=auth_headers, params={"limit": 10})
    first_data = first_response.json()
    cursor = first_data["next_cursor"]

    # Проверяем что курсор не пустой
    assert cursor is not None

    # Вторая страница с курсором
    response = await client.get("/api/v2/conversations/", headers=auth_headers, params={"limit": 10, "cursor": cursor})
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) == 10
    # Беседы должны отличаться от первой страницы
    first_ids = {item["id"] for item in first_data["items"]}
    second_ids = {item["id"] for item in data["items"]}
    assert len(first_ids.intersection(second_ids)) == 0


@pytest.mark.asyncio
async def test_get_conversations_last_page(
    client: AsyncClient, auth_headers: dict[str, str], test_conversations: list
) -> None:
    """Тест: получение последней страницы"""
    # Запрашиваем больше чем есть
    response = await client.get("/api/v2/conversations/", headers=auth_headers, params={"limit": 25})
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) == 25
    assert data["has_next"] is False
    assert data["next_cursor"] is None


@pytest.mark.asyncio
async def test_get_conversations_invalid_cursor(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: получение с невалидным курсором"""
    response = await client.get("/api/v2/conversations/", headers=auth_headers, params={"cursor": "invalid_cursor"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_conversations_limit_validation(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: валидация limit параметра"""
    # Слишком большой limit
    response = await client.get("/api/v2/conversations/", headers=auth_headers, params={"limit": 150})
    # Должен использовать максимальное значение (100)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_conversations_empty_db(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: получение бесед из пустой БД"""
    response = await client.get("/api/v2/conversations/", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) == 0
    assert data["has_next"] is False
    assert data["next_cursor"] is None


# ============================================================
# POST /conversations - создание новой беседы
# ============================================================


@pytest.mark.asyncio
async def test_create_conversation_success(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: успешное создание беседы"""
    response = await client.post("/api/v2/conversations/", headers=auth_headers, json={"title": "My New Conversation"})
    assert response.status_code == 201

    data = response.json()
    assert "id" in data
    assert data["title"] == "My New Conversation"
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_create_conversation_default_title(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: создание беседы с дефолтным названием"""
    response = await client.post("/api/v2/conversations/", headers=auth_headers, json={})
    assert response.status_code == 201

    data = response.json()
    assert data["title"] == "New conversation"


@pytest.mark.asyncio
async def test_create_conversation_unauthorized(client: AsyncClient) -> None:
    """Тест: создание беседы без авторизации"""
    response = await client.post("/api/v2/conversations/", json={"title": "Test Conversation"})
    assert response.status_code == 401


# ============================================================
# PATCH /conversations/{id} - обновление беседы
# ============================================================


@pytest.mark.asyncio
async def test_update_conversation_title(
    client: AsyncClient, auth_headers: dict[str, str], test_conversation: ConversationModel
) -> None:
    """Тест: обновление названия беседы"""
    response = await client.patch(
        f"/api/v2/conversations/{test_conversation.id}", headers=auth_headers, json={"title": "Updated Title"}
    )
    assert response.status_code == 200

    data = response.json()
    assert data["title"] == "Updated Title"


@pytest.mark.asyncio
async def test_update_conversation_to_archive(
    client: AsyncClient, auth_headers: dict[str, str], test_conversation: ConversationModel
) -> None:
    """Тест: отправка беседы в архив"""
    response = await client.patch(
        f"/api/v2/conversations/{test_conversation.id}", headers=auth_headers, json={"is_archived": True}
    )
    assert response.status_code == 200

    data = response.json()
    assert data["is_archived"] is True


@pytest.mark.asyncio
async def test_update_conversation_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: обновление несуществующей беседы"""
    import uuid

    response = await client.patch(
        f"/api/v2/conversations/{uuid.uuid4()}", headers=auth_headers, json={"title": "Updated"}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_conversation_unauthorized(client: AsyncClient) -> None:
    """Тест: обновление без авторизации"""
    import uuid

    response = await client.patch(f"/api/v2/conversations/{uuid.uuid4()}", json={"title": "Updated"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_conversation_empty_data(
    client: AsyncClient, auth_headers: dict[str, str], test_conversation: ConversationModel
) -> None:
    """Тест: обновление с пустыми данными"""
    response = await client.patch(f"/api/v2/conversations/{test_conversation.id}", headers=auth_headers, json={})
    # Должно вернуть 200 без изменений
    assert response.status_code == 200


# ============================================================
# DELETE /conversations/{id} - удаление беседы
# ============================================================


@pytest.mark.asyncio
async def test_delete_conversation_success(
    client: AsyncClient, auth_headers: dict[str, str], test_conversation: ConversationModel
) -> None:
    """Тест: успешное удаление беседы"""
    response = await client.delete(f"/api/v2/conversations/{test_conversation.id}", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert "message" in data


@pytest.mark.asyncio
async def test_delete_conversation_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: удаление несуществующей беседы"""
    import uuid

    response = await client.delete(f"/api/v2/conversations/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_conversation_unauthorized(client: AsyncClient) -> None:
    """Тест: удаление без авторизации"""
    import uuid

    response = await client.delete(f"/api/v2/conversations/{uuid.uuid4()}")
    assert response.status_code == 401


# ============================================================
# Проверка доступа к чужим беседам
# ============================================================


@pytest.mark.asyncio
async def test_get_other_user_conversation(
    client: AsyncClient, admin_headers: dict[str, str], test_conversation: ConversationModel
) -> None:
    """Тест: попытка получить беседу другого пользователя"""
    # test_conversation принадлежит test_user, а запрашивает admin
    # GET /conversations/{id} не реализован, но если бы был - должен вернуть 404
    # Сейчас проверяем только через список
    pass


@pytest.mark.asyncio
async def test_update_other_user_conversation(
    client: AsyncClient, admin_headers: dict[str, str], test_conversation: ConversationModel
) -> None:
    """Тест: попытка обновить беседу другого пользователя"""
    response = await client.patch(
        f"/api/v2/conversations/{test_conversation.id}", headers=admin_headers, json={"title": "Hacked"}
    )
    assert response.status_code == 404  # Не найдена (не его беседа)


@pytest.mark.asyncio
async def test_delete_other_user_conversation(
    client: AsyncClient, admin_headers: dict[str, str], test_conversation: ConversationModel
) -> None:
    """Тест: попытка удалить беседу другого пользователя"""
    response = await client.delete(f"/api/v2/conversations/{test_conversation.id}", headers=admin_headers)
    assert response.status_code == 404  # Не найдена (не его беседа)
