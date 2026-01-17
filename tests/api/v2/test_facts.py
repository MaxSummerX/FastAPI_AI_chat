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

from app.models import Fact as FactModel


# ============================================================
# GET /facts - курсорная пагинация
# ============================================================


@pytest.mark.asyncio
async def test_get_facts_unauthorized(client: AsyncClient) -> None:
    """Тест: неавторизованный запрос к facts"""
    response = await client.get("/api/v2/facts/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_facts_empty(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: получение фактов когда их нет"""
    response = await client.get("/api/v2/facts/", headers=auth_headers)
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
    response = await client.get("/api/v2/facts/", headers=auth_headers, params={"limit": 15})
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
    first_response = await client.get("/api/v2/facts/", headers=auth_headers, params={"limit": 10})
    first_data = first_response.json()
    cursor = first_data["next_cursor"]

    # Вторая страница
    response = await client.get(
        "/api/v2/facts/",
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

        response = await client.get("/api/v2/facts/", headers=auth_headers, params=params)
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
        "/api/v2/facts/",
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
    response = await client.get("/api/v2/facts/", headers=auth_headers, params={"limit": 10})
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
        "/api/v2/facts/",
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
    response_active = await client.get("/api/v2/facts/", headers=auth_headers, params={"limit": 100})
    active_data = response_active.json()
    assert len(active_data["items"]) == 29

    # С include_inactive - все факты
    response_all = await client.get(
        "/api/v2/facts/",
        headers=auth_headers,
        params={"include_inactive": True, "limit": 100},
    )
    all_data = response_all.json()
    assert len(all_data["items"]) == 30


@pytest.mark.asyncio
async def test_get_facts_limit_validation(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: валидация limit параметра"""
    # Слишком большой limit - использует максимум
    response = await client.get("/api/v2/facts/", headers=auth_headers, params={"limit": 150})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_facts_limit_minimum(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: limit меньше минимума возвращает ошибку валидации"""
    response = await client.get("/api/v2/facts/", headers=auth_headers, params={"limit": 0})
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
# POST /facts - создание факта
# ============================================================


@pytest.mark.asyncio
async def test_create_fact_unauthorized(client: AsyncClient) -> None:
    """Тест: создание факта без авторизации"""
    response = await client.post(
        "/api/v2/facts/",
        json={
            "content": "Test fact about user",
            "category": "personal",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_fact_success(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: успешное создание факта"""
    response = await client.post(
        "/api/v2/facts/",
        headers=auth_headers,
        json={
            "content": "User loves Python programming",
            "category": "professional",
            "confidence": 0.9,
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert "id" in data
    assert data["content"] == "User loves Python programming"
    assert data["category"] == "professional"
    assert data["confidence"] == 0.9
    assert data["source_type"] == "user_provided"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_create_fact_default_category(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: создание факта с категорией по умолчанию (personal)"""
    response = await client.post(
        "/api/v2/facts/",
        headers=auth_headers,
        json={
            "content": "Another fact",
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["category"] == "personal"


@pytest.mark.asyncio
async def test_create_fact_with_metadata(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: создание факта с метаданными"""
    response = await client.post(
        "/api/v2/facts/",
        headers=auth_headers,
        json={
            "content": "Fact with metadata",
            "category": "technical",
            "metadata_": {"source": "manual", "verified": True},
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["metadata_"] == {"source": "manual", "verified": True}


@pytest.mark.asyncio
async def test_create_fact_empty_content(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: создание факта с пустым контентом"""
    response = await client.post(
        "/api/v2/facts/",
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
        "/api/v2/facts/",
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
        "/api/v2/facts/",
        headers=auth_headers,
        json={
            "content": "Valid content for fact",
            "confidence": 1.5,
        },
    )
    assert response.status_code == 422


# ============================================================
# PATCH /facts/{fact_id} - обновление факта
# ============================================================


@pytest.mark.asyncio
async def test_update_fact_unauthorized(client: AsyncClient, test_fact: FactModel) -> None:
    """Тест: обновление факта без авторизации"""
    response = await client.patch(
        f"/api/v2/facts/{test_fact.id}",
        json={"content": "Updated content"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_fact_success(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_fact: FactModel,
) -> None:
    """Тест: успешное обновление факта"""
    response = await client.patch(
        f"/api/v2/facts/{test_fact.id}",
        headers=auth_headers,
        json={
            "content": "Updated fact content",
            "category": "learning",
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(test_fact.id)
    assert data["content"] == "Updated fact content"
    assert data["category"] == "learning"


@pytest.mark.asyncio
async def test_update_fact_partial(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_fact: FactModel,
) -> None:
    """Тест: частичное обновление факта"""
    original_content = test_fact.content

    response = await client.patch(
        f"/api/v2/facts/{test_fact.id}",
        headers=auth_headers,
        json={"confidence": 0.7},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["confidence"] == 0.7
    assert data["content"] == original_content


@pytest.mark.asyncio
async def test_update_fact_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: обновление несуществующего факта"""
    import uuid

    response = await client.patch(
        f"/api/v2/facts/{uuid.uuid4()}",
        headers=auth_headers,
        json={"content": "Updated"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_fact_inactive(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_fact: FactModel,
    db_session: AsyncSession,
) -> None:
    """Тест: обновление неактивного факта"""
    test_fact.is_active = False
    await db_session.commit()

    response = await client.patch(
        f"/api/v2/facts/{test_fact.id}",
        headers=auth_headers,
        json={"content": "Try to update inactive"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_fact_other_user(
    client: AsyncClient,
    admin_headers: dict[str, str],
    test_fact: FactModel,
) -> None:
    """Тест: попытка обновить факт другого пользователя"""
    response = await client.patch(
        f"/api/v2/facts/{test_fact.id}",
        headers=admin_headers,
        json={"content": "Hacked!"},
    )
    assert response.status_code == 404


# ============================================================
# DELETE /facts/{fact_id} - удаление факта
# ============================================================


@pytest.mark.asyncio
async def test_delete_fact_unauthorized(client: AsyncClient, test_fact: FactModel) -> None:
    """Тест: удаление факта без авторизации"""
    response = await client.delete(f"/api/v2/facts/{test_fact.id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_fact_success(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_fact: FactModel,
    db_session: AsyncSession,
) -> None:
    """Тест: успешное удаление факта (мягкое)"""
    response = await client.delete(f"/api/v2/facts/{test_fact.id}", headers=auth_headers)
    assert response.status_code == 204

    # Проверяем что факт помечен как неактивный
    await db_session.refresh(test_fact)
    assert test_fact.is_active is False


@pytest.mark.asyncio
async def test_delete_fact_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: удаление несуществующего факта"""
    import uuid

    response = await client.delete(f"/api/v2/facts/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_fact_inactive(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_fact: FactModel,
    db_session: AsyncSession,
) -> None:
    """Тест: удаление уже неактивного факта"""
    test_fact.is_active = False
    await db_session.commit()

    response = await client.delete(f"/api/v2/facts/{test_fact.id}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_fact_other_user(
    client: AsyncClient,
    admin_headers: dict[str, str],
    test_fact: FactModel,
) -> None:
    """Тест: попытка удалить факт другого пользователя"""
    response = await client.delete(f"/api/v2/facts/{test_fact.id}", headers=admin_headers)
    assert response.status_code == 404
