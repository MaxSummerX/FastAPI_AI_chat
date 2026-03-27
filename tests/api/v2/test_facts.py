"""
Тесты для fact endpoints API v2.

Покрывает все основные сценарии:
- Получение фактов с курсорной пагинацией
- Фильтрация по категории
- Создание, обновление, удаление фактов
- Обработка ошибок
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.fact import Fact as FactModel


# ============================================================
# GET /facts - курсорная пагинация
# ============================================================


@pytest.mark.asyncio
async def test_get_facts_unauthorized(client: AsyncClient) -> None:
    """Тест: неавторизованный запрос к facts"""
    response = await client.get("/api/v2/facts")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_facts_empty(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: получение фактов когда их нет"""
    response = await client.get("/api/v2/facts", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert "next_cursor" in data
    assert "has_next" in data
    assert len(data["items"]) == 0
    assert data["has_next"] is False
    assert data["next_cursor"] is None


@pytest.mark.asyncio
async def test_get_facts_first_page(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_facts: list[FactModel],
) -> None:
    """Тест: первая страница фактов (без cursor)"""
    response = await client.get("/api/v2/facts", headers=auth_headers, params={"limit": 15})
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) == 15
    assert data["has_next"] is True
    assert data["next_cursor"] is not None


@pytest.mark.asyncio
async def test_get_facts_with_cursor(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_facts: list[FactModel],
) -> None:
    """Тест: вторая страница фактов (с cursor)"""
    # Первая страница
    first_response = await client.get("/api/v2/facts", headers=auth_headers, params={"limit": 10})
    first_data = first_response.json()
    cursor = first_data["next_cursor"]

    # Вторая страница
    response = await client.get(
        "/api/v2/facts",
        headers=auth_headers,
        params={"limit": 10, "cursor": cursor},
    )
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) == 10
    assert data["has_next"] is True


@pytest.mark.asyncio
async def test_get_facts_pagination_to_end(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_facts: list[FactModel],
) -> None:
    """Тест: пагинация до конца (все факты загружены)"""
    all_items = []
    cursor = None

    for _ in range(10):
        params = {"limit": 10}
        if cursor:
            params["cursor"] = cursor

        response = await client.get("/api/v2/facts", headers=auth_headers, params=params)
        data = response.json()

        all_items.extend(data["items"])

        if not data["has_next"]:
            break

        cursor = data["next_cursor"]

    # Должны загрузить все 30 фактов
    assert len(all_items) == 30


@pytest.mark.asyncio
async def test_get_facts_invalid_cursor(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: использование невалидного курсора"""
    response = await client.get(
        "/api/v2/facts",
        headers=auth_headers,
        params={"cursor": "invalid_cursor_base64"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_facts_ordering_desc(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_facts: list[FactModel],
) -> None:
    """Тест: проверка правильности сортировки (от нового к старому)"""
    response = await client.get("/api/v2/facts", headers=auth_headers, params={"limit": 10})
    assert response.status_code == 200

    data = response.json()
    items = data["items"]

    # Проверяем сортировку от НОВОГО к СТАРОМУ (DESC)
    for i in range(len(items) - 1):
        current_timestamp = items[i]["created_at"]
        next_timestamp = items[i + 1]["created_at"]
        assert current_timestamp >= next_timestamp


@pytest.mark.asyncio
async def test_get_facts_filter_by_category(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_facts: list[FactModel],
) -> None:
    """Тест: фильтрация фактов по категории"""
    response = await client.get(
        "/api/v2/facts",
        headers=auth_headers,
        params={"category": "personal", "limit": 100},
    )
    assert response.status_code == 200

    data = response.json()
    # Все факты должны быть категории personal
    for fact in data["items"]:
        assert fact["category"] == "personal"


@pytest.mark.asyncio
async def test_get_facts_include_inactive(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_facts: list[FactModel],
) -> None:
    """Тест: включение неактивных фактов"""
    # Деактивируем первый факт
    test_facts[0].is_active = False
    await db_session.commit()

    # Без include_inactive - неактивные не возвращаются
    response_active = await client.get("/api/v2/facts", headers=auth_headers, params={"limit": 100})
    active_data = response_active.json()
    assert len(active_data["items"]) == 29

    # С include_inactive - все факты
    response_all = await client.get(
        "/api/v2/facts",
        headers=auth_headers,
        params={"include_inactive": True, "limit": 100},
    )
    all_data = response_all.json()
    assert len(all_data["items"]) == 30


@pytest.mark.asyncio
async def test_get_facts_limit_validation(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: валидация limit параметра"""
    # Слишком большой limit - использует максимум
    response = await client.get("/api/v2/facts", headers=auth_headers, params={"limit": 150})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_facts_limit_minimum(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: limit меньше минимума возвращает ошибку валидации"""
    response = await client.get("/api/v2/facts", headers=auth_headers, params={"limit": 0})
    assert response.status_code == 422


# ============================================================
# GET /facts/{fact_id} - получение факта по ID
# ============================================================


@pytest.mark.asyncio
async def test_get_fact_unauthorized(client: AsyncClient, test_fact: FactModel) -> None:
    """Тест: получение факта без авторизации"""
    response = await client.get(f"/api/v2/facts/{test_fact.id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_fact_success(client: AsyncClient, auth_headers: dict[str, str], test_fact: FactModel) -> None:
    """Тест: успешное получение факта"""
    response = await client.get(f"/api/v2/facts/{test_fact.id}", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(test_fact.id)
    assert data["content"] == test_fact.content
    assert data["category"] == test_fact.category


@pytest.mark.asyncio
async def test_get_fact_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: получение несуществующего факта"""
    import uuid

    response = await client.get(f"/api/v2/facts/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_fact_inactive(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_fact: FactModel,
    db_session: AsyncSession,
) -> None:
    """Тест: получение неактивного факта"""
    test_fact.is_active = False
    await db_session.commit()

    response = await client.get(f"/api/v2/facts/{test_fact.id}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_fact_other_user(
    client: AsyncClient,
    admin_headers: dict[str, str],
    test_fact: FactModel,
) -> None:
    """Тест: попытка получить факт другого пользователя"""
    response = await client.get(f"/api/v2/facts/{test_fact.id}", headers=admin_headers)
    assert response.status_code == 404


# ============================================================
# POST /facts - создание факта (с BackgroundTasks)
# ============================================================


@pytest.mark.asyncio
async def test_create_fact_unauthorized(client: AsyncClient) -> None:
    """Тест: создание факта без авторизации"""
    response = await client.post(
        "/api/v2/facts",
        json={
            "content": "Test fact about user",
            "category": "personal",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_fact_success(
    client_with_mocked_memory_sync: AsyncClient,
    auth_headers_memory_sync: dict[str, str],
) -> None:
    """Тест: успешное создание факта (через background task)"""
    import asyncio

    response = await client_with_mocked_memory_sync.post(
        "/api/v2/facts",
        headers=auth_headers_memory_sync,
        json={
            "content": "User loves Python programming",
            "category": "professional",
            "confidence": 0.9,
        },
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "processing"

    # Ждём выполнения background task
    await asyncio.sleep(0.1)

    # Проверяем через GET всех фактов
    response = await client_with_mocked_memory_sync.get("/api/v2/facts", headers=auth_headers_memory_sync)
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) > 0

    # Находим созданный факт
    fact = next((f for f in data["items"] if f["content"] == "User loves Python programming"), None)
    assert fact is not None
    assert fact["category"] == "professional"
    assert fact["confidence"] == 0.9
    assert fact["source_type"] == "user_provided"
    assert fact["is_active"] is True


@pytest.mark.asyncio
async def test_create_fact_default_category(
    client_with_mocked_memory_sync: AsyncClient,
    auth_headers_memory_sync: dict[str, str],
) -> None:
    """Тест: создание факта с категорией по умолчанию (personal)"""
    import asyncio

    response = await client_with_mocked_memory_sync.post(
        "/api/v2/facts",
        headers=auth_headers_memory_sync,
        json={
            "content": "Another fact",
        },
    )
    assert response.status_code == 202

    # Ждём выполнения background task
    await asyncio.sleep(0.1)

    # Проверяем через GET всех фактов
    response = await client_with_mocked_memory_sync.get("/api/v2/facts", headers=auth_headers_memory_sync)
    assert response.status_code == 200
    data = response.json()
    fact = next((f for f in data["items"] if f["content"] == "Another fact"), None)
    assert fact is not None
    assert fact["category"] == "personal"


@pytest.mark.asyncio
async def test_create_fact_with_metadata(
    client_with_mocked_memory_sync: AsyncClient,
    auth_headers_memory_sync: dict[str, str],
) -> None:
    """Тест: создание факта с метаданными"""
    import asyncio

    response = await client_with_mocked_memory_sync.post(
        "/api/v2/facts",
        headers=auth_headers_memory_sync,
        json={
            "content": "Fact with metadata",
            "category": "technical",
            "metadata_": {"source": "manual", "verified": True},
        },
    )
    assert response.status_code == 202

    # Ждём выполнения background task
    await asyncio.sleep(0.1)

    # Проверяем через GET всех фактов
    response = await client_with_mocked_memory_sync.get("/api/v2/facts", headers=auth_headers_memory_sync)
    assert response.status_code == 200
    data = response.json()
    fact = next((f for f in data["items"] if f["content"] == "Fact with metadata"), None)
    assert fact is not None
    assert fact["metadata_"] == {"source": "manual", "verified": True}


@pytest.mark.asyncio
async def test_create_fact_empty_content(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: создание факта с пустым контентом"""
    response = await client.post(
        "/api/v2/facts",
        headers=auth_headers,
        json={
            "content": "   ",
            "category": "personal",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_fact_content_too_short(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: контент короче минимума (5 символов)"""
    response = await client.post(
        "/api/v2/facts",
        headers=auth_headers,
        json={
            "content": "abc",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_fact_invalid_confidence(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: невалидное значение confidence"""
    response = await client.post(
        "/api/v2/facts",
        headers=auth_headers,
        json={
            "content": "Valid content for fact",
            "confidence": 1.5,
        },
    )
    assert response.status_code == 422


# ============================================================
# PUT /facts/{fact_id} - обновление факта (с BackgroundTasks)
# ============================================================


@pytest.mark.asyncio
async def test_update_fact_unauthorized(client: AsyncClient, test_fact: FactModel) -> None:
    """Тест: обновление факта без авторизации"""
    response = await client.put(
        f"/api/v2/facts/{test_fact.id}",
        json={"content": "Updated content"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_fact_success(
    client_with_mocked_memory_sync: AsyncClient,
    auth_headers_memory_sync: dict[str, str],
    test_fact: FactModel,
) -> None:
    """Тест: успешное обновление факта (через background task)"""
    import asyncio

    response = await client_with_mocked_memory_sync.put(
        f"/api/v2/facts/{test_fact.id}",
        headers=auth_headers_memory_sync,
        json={
            "content": "Updated fact content",
            "category": "learning",
        },
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "processing"

    # Ждём выполнения background task
    await asyncio.sleep(0.1)

    # Проверяем через GET
    response = await client_with_mocked_memory_sync.get(
        f"/api/v2/facts/{test_fact.id}",
        headers=auth_headers_memory_sync,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_fact.id)
    assert data["content"] == "Updated fact content"
    assert data["category"] == "learning"


@pytest.mark.asyncio
async def test_update_fact_confidence(
    client_with_mocked_memory_sync: AsyncClient,
    auth_headers_memory_sync: dict[str, str],
    test_fact: FactModel,
) -> None:
    """
    Тест: обновление confidence факта.

    При обновлении требуется отправить все поля (content обязателен),
    т.к. происходит перевекторизация в Qdrant.
    """
    import asyncio

    original_content = test_fact.content
    original_category = test_fact.category

    response = await client_with_mocked_memory_sync.put(
        f"/api/v2/facts/{test_fact.id}",
        headers=auth_headers_memory_sync,
        json={
            "content": original_content,  # Обязательно при обновлении (перевекторизация)
            "category": original_category,
            "confidence": 0.7,
        },
    )
    assert response.status_code == 202

    # Ждём выполнения background task
    await asyncio.sleep(0.1)

    # Проверяем через GET
    response = await client_with_mocked_memory_sync.get(
        f"/api/v2/facts/{test_fact.id}",
        headers=auth_headers_memory_sync,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["confidence"] == 0.7
    # Content и category не изменились
    assert data["content"] == original_content
    assert data["category"] == original_category


@pytest.mark.asyncio
async def test_update_fact_not_found(
    client_with_mocked_memory_sync: AsyncClient,
    auth_headers_memory_sync: dict[str, str],
) -> None:
    """Тест: обновление несуществующего факта"""
    import uuid

    response = await client_with_mocked_memory_sync.put(
        f"/api/v2/facts/{uuid.uuid4()}",
        headers=auth_headers_memory_sync,
        json={"content": "Updated"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_fact_inactive(
    client_with_mocked_memory_sync: AsyncClient,
    auth_headers_memory_sync: dict[str, str],
    test_fact: FactModel,
    db_session: AsyncSession,
) -> None:
    """Тест: обновление неактивного факта"""
    test_fact.is_active = False
    await db_session.commit()

    response = await client_with_mocked_memory_sync.put(
        f"/api/v2/facts/{test_fact.id}",
        headers=auth_headers_memory_sync,
        json={"content": "Try to update inactive"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_fact_other_user(
    client_with_mocked_memory_sync: AsyncClient,
    admin_headers_memory_sync: dict[str, str],
    test_fact: FactModel,
) -> None:
    """Тест: попытка обновить факт другого пользователя (admin обновляет факт пользователя)"""
    # Admin не может обновлять факты других пользователей - вернёт 404
    response = await client_with_mocked_memory_sync.put(
        f"/api/v2/facts/{test_fact.id}",
        headers=admin_headers_memory_sync,  # Admin токен с замоканным memory
        json={
            "content": "Hacked!",
            "category": test_fact.category,
        },
    )
    assert response.status_code == 404


# ============================================================
# DELETE /facts/{fact_id} - удаление факта
# ============================================================


@pytest.mark.asyncio
async def test_delete_fact_unauthorized(client_with_mocked_memory_sync: AsyncClient, test_fact: FactModel) -> None:
    """Тест: удаление факта без авторизации"""
    response = await client_with_mocked_memory_sync.delete(f"/api/v2/facts/{test_fact.id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_fact_success(
    client_with_mocked_memory_sync: AsyncClient,
    auth_headers_memory_sync: dict[str, str],
    test_fact: FactModel,
    db_session: AsyncSession,
) -> None:
    """Тест: успешное удаление факта (мягкое)"""
    response = await client_with_mocked_memory_sync.delete(
        f"/api/v2/facts/{test_fact.id}", headers=auth_headers_memory_sync
    )
    assert response.status_code == 204

    # Проверяем что факт помечен как неактивный
    await db_session.refresh(test_fact)
    assert test_fact.is_active is False


@pytest.mark.asyncio
async def test_delete_fact_not_found(
    client_with_mocked_memory_sync: AsyncClient, auth_headers_memory_sync: dict[str, str]
) -> None:
    """Тест: удаление несуществующего факта"""
    import uuid

    response = await client_with_mocked_memory_sync.delete(
        f"/api/v2/facts/{uuid.uuid4()}", headers=auth_headers_memory_sync
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_fact_inactive(
    client_with_mocked_memory_sync: AsyncClient,
    auth_headers_memory_sync: dict[str, str],
    test_fact: FactModel,
    db_session: AsyncSession,
) -> None:
    """Тест: удаление уже неактивного факта"""
    test_fact.is_active = False
    await db_session.commit()

    response = await client_with_mocked_memory_sync.delete(
        f"/api/v2/facts/{test_fact.id}", headers=auth_headers_memory_sync
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_fact_other_user(
    client_with_mocked_memory_sync: AsyncClient,
    admin_headers_memory_sync: dict[str, str],
    test_fact: FactModel,
) -> None:
    """Тест: попытка удалить факт другого пользователя"""
    response = await client_with_mocked_memory_sync.delete(
        f"/api/v2/facts/{test_fact.id}", headers=admin_headers_memory_sync
    )
    assert response.status_code == 404
