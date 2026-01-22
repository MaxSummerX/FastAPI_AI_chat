"""
Тесты для prompt endpoints API v2.

Покрывает все основные сценарии:
- Получение промптов с курсорной пагинацией
- Создание, обновление, удаление промптов
- Обработка ошибок
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompts import Prompts as PromptModel


# ============================================================
# GET /prompts - курсорная пагинация
# ============================================================


@pytest.mark.asyncio
async def test_get_prompts_unauthorized(client: AsyncClient) -> None:
    """Тест: неавторизованный запрос к prompts"""
    response = await client.get("/api/v2/prompts")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_prompts_empty(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: получение промптов когда их нет"""
    response = await client.get("/api/v2/prompts", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert "next_cursor" in data
    assert "has_next" in data
    assert len(data["items"]) == 0
    assert data["has_next"] is False
    assert data["next_cursor"] is None


@pytest.mark.asyncio
async def test_get_prompts_first_page(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_prompts: list[PromptModel],
) -> None:
    """Тест: первая страница промптов (без cursor)"""
    response = await client.get("/api/v2/prompts", headers=auth_headers, params={"limit": 15})
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) == 15
    assert data["has_next"] is True
    assert data["next_cursor"] is not None


@pytest.mark.asyncio
async def test_get_prompts_with_cursor(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_prompts: list[PromptModel],
) -> None:
    """Тест: вторая страница промптов (с cursor)"""
    # Первая страница
    first_response = await client.get("/api/v2/prompts", headers=auth_headers, params={"limit": 10})
    first_data = first_response.json()
    cursor = first_data["next_cursor"]

    # Вторая страница
    response = await client.get(
        "/api/v2/prompts",
        headers=auth_headers,
        params={"limit": 10, "cursor": cursor},
    )
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) == 10
    assert data["has_next"] is True


@pytest.mark.asyncio
async def test_get_prompts_pagination_to_end(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_prompts: list[PromptModel],
) -> None:
    """Тест: пагинация до конца (все промпты загружены)"""
    all_items = []
    cursor = None

    for _ in range(10):
        params = {"limit": 10}
        if cursor:
            params["cursor"] = cursor

        response = await client.get("/api/v2/prompts", headers=auth_headers, params=params)
        data = response.json()

        all_items.extend(data["items"])

        if not data["has_next"]:
            break

        cursor = data["next_cursor"]

    # Должны загрузить все 30 промптов
    assert len(all_items) == 30


@pytest.mark.asyncio
async def test_get_prompts_invalid_cursor(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: использование невалидного курсора"""
    response = await client.get(
        "/api/v2/prompts",
        headers=auth_headers,
        params={"cursor": "invalid_cursor_base64"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_prompts_ordering_desc(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_prompts: list[PromptModel],
) -> None:
    """Тест: проверка правильности сортировки (от нового к старому)"""
    response = await client.get("/api/v2/prompts", headers=auth_headers, params={"limit": 10})
    assert response.status_code == 200

    data = response.json()
    items = data["items"]

    # Проверяем сортировку от НОВОГО к СТАРОМУ (DESC)
    for i in range(len(items) - 1):
        current_timestamp = items[i]["created_at"]
        next_timestamp = items[i + 1]["created_at"]
        assert current_timestamp >= next_timestamp


@pytest.mark.asyncio
async def test_get_prompts_include_inactive(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_prompts: list[PromptModel],
) -> None:
    """Тест: включение неактивных промптов"""
    # Деактивируем первый промпт
    test_prompts[0].is_active = False
    await db_session.commit()

    # Без include_inactive - неактивные не возвращаются
    response_active = await client.get("/api/v2/prompts", headers=auth_headers, params={"limit": 100})
    active_data = response_active.json()
    assert len(active_data["items"]) == 29

    # С include_inactive - все промпты
    response_all = await client.get(
        "/api/v2/prompts",
        headers=auth_headers,
        params={"include_inactive": True, "limit": 100},
    )
    all_data = response_all.json()
    assert len(all_data["items"]) == 30


@pytest.mark.asyncio
async def test_get_prompts_limit_validation(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: валидация limit параметра"""
    # Слишком большой limit - использует максимум
    response = await client.get("/api/v2/prompts", headers=auth_headers, params={"limit": 150})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_prompts_limit_minimum(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: limit меньше минимума возвращает ошибку валидации"""
    response = await client.get("/api/v2/prompts", headers=auth_headers, params={"limit": 0})
    assert response.status_code == 422


# ============================================================
# GET /prompts/{prompt_id} - получение промпта по ID
# ============================================================


@pytest.mark.asyncio
async def test_get_prompt_unauthorized(client: AsyncClient, test_prompt: PromptModel) -> None:
    """Тест: получение промпта без авторизации"""
    response = await client.get(f"/api/v2/prompts/{test_prompt.id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_prompt_success(client: AsyncClient, auth_headers: dict[str, str], test_prompt: PromptModel) -> None:
    """Тест: успешное получение промпта"""
    response = await client.get(f"/api/v2/prompts/{test_prompt.id}", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(test_prompt.id)
    assert data["title"] == test_prompt.title
    assert data["content"] == test_prompt.content


@pytest.mark.asyncio
async def test_get_prompt_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: получение несуществующего промпта"""

    response = await client.get(f"/api/v2/prompts/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_prompt_inactive(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_prompt: PromptModel,
    db_session: AsyncSession,
) -> None:
    """Тест: получение неактивного промпта"""
    test_prompt.is_active = False
    await db_session.commit()

    response = await client.get(f"/api/v2/prompts/{test_prompt.id}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_prompt_other_user(
    client: AsyncClient,
    admin_headers: dict[str, str],
    test_prompt: PromptModel,
) -> None:
    """Тест: попытка получить промпт другого пользователя"""
    response = await client.get(f"/api/v2/prompts/{test_prompt.id}", headers=admin_headers)
    assert response.status_code == 404


# ============================================================
# POST /prompts - создание промпта
# ============================================================


@pytest.mark.asyncio
async def test_create_prompt_unauthorized(client: AsyncClient) -> None:
    """Тест: создание промпта без авторизации"""
    response = await client.post(
        "/api/v2/prompts",
        json={
            "title": "Test Prompt",
            "content": "You are a helpful assistant",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_prompt_success(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: успешное создание промпта"""
    response = await client.post(
        "/api/v2/prompts",
        headers=auth_headers,
        json={
            "title": "Code Helper",
            "content": "You are an expert Python programmer",
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert "id" in data
    assert data["title"] == "Code Helper"
    assert data["content"] == "You are an expert Python programmer"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_create_prompt_without_title(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: создание промпта без заголовка"""
    response = await client.post(
        "/api/v2/prompts",
        headers=auth_headers,
        json={
            "content": "Simple prompt content",
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["title"] is None
    assert data["content"] == "Simple prompt content"


@pytest.mark.asyncio
async def test_create_prompt_with_metadata(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: создание промпта с метаданными"""
    response = await client.post(
        "/api/v2/prompts",
        headers=auth_headers,
        json={
            "title": "Metadata Prompt",
            "content": "Content",
            "metadata_": {"version": 1, "tags": ["coding", "python"]},
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["metadata_"] == {"version": 1, "tags": ["coding", "python"]}


@pytest.mark.asyncio
async def test_create_prompt_empty_content(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: создание промпта с пустым контентом"""
    response = await client.post(
        "/api/v2/prompts",
        headers=auth_headers,
        json={
            "title": "Empty",
            "content": "",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_prompt_title_too_long(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: заголовок длиннее максимума (255 символов)"""
    response = await client.post(
        "/api/v2/prompts",
        headers=auth_headers,
        json={
            "title": "x" * 256,
            "content": "Valid content",
        },
    )
    assert response.status_code == 422


# ============================================================
# PUT /prompts/{prompt_id} - обновление промпта
# ============================================================


@pytest.mark.asyncio
async def test_update_prompt_unauthorized(client: AsyncClient, test_prompt: PromptModel) -> None:
    """Тест: обновление промпта без авторизации"""
    response = await client.put(
        f"/api/v2/prompts/{test_prompt.id}",
        json={"content": "Updated content"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_prompt_success(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_prompt: PromptModel,
) -> None:
    """Тест: успешное обновление промпта"""
    response = await client.put(
        f"/api/v2/prompts/{test_prompt.id}",
        headers=auth_headers,
        json={
            "title": "Updated Title",
            "content": "Updated content for prompt",
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(test_prompt.id)
    assert data["title"] == "Updated Title"
    assert data["content"] == "Updated content for prompt"


@pytest.mark.asyncio
async def test_update_prompt_partial(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_prompt: PromptModel,
) -> None:
    """Тест: частичное обновление промпта"""
    original_content = test_prompt.content

    response = await client.put(
        f"/api/v2/prompts/{test_prompt.id}",
        headers=auth_headers,
        json={"title": "New title only"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["title"] == "New title only"
    assert data["content"] == original_content


@pytest.mark.asyncio
async def test_update_prompt_deactivate(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_prompt: PromptModel,
) -> None:
    """Тест: деактивация промпта"""
    response = await client.put(
        f"/api/v2/prompts/{test_prompt.id}",
        headers=auth_headers,
        json={"is_active": False},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["is_active"] is False


@pytest.mark.asyncio
async def test_update_prompt_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: обновление несуществующего промпта"""

    response = await client.put(
        f"/api/v2/prompts/{uuid.uuid4()}",
        headers=auth_headers,
        json={"content": "Updated"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_prompt_other_user(
    client: AsyncClient,
    admin_headers: dict[str, str],
    test_prompt: PromptModel,
) -> None:
    """Тест: попытка обновить промпт другого пользователя"""
    response = await client.put(
        f"/api/v2/prompts/{test_prompt.id}",
        headers=admin_headers,
        json={"content": "Hacked!"},
    )
    assert response.status_code == 404


# ============================================================
# DELETE /prompts/{prompt_id} - удаление промпта
# ============================================================


@pytest.mark.asyncio
async def test_delete_prompt_unauthorized(client: AsyncClient, test_prompt: PromptModel) -> None:
    """Тест: удаление промпта без авторизации"""
    response = await client.delete(f"/api/v2/prompts/{test_prompt.id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_prompt_success(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_prompt: PromptModel,
    db_session: AsyncSession,
) -> None:
    """Тест: успешное удаление промпта (мягкое)"""
    response = await client.delete(f"/api/v2/prompts/{test_prompt.id}", headers=auth_headers)
    assert response.status_code == 204

    # Проверяем что промпт помечен как неактивный
    await db_session.refresh(test_prompt)
    assert test_prompt.is_active is False


@pytest.mark.asyncio
async def test_delete_prompt_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: удаление несуществующего промпта"""

    response = await client.delete(f"/api/v2/prompts/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_prompt_inactive(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_prompt: PromptModel,
    db_session: AsyncSession,
) -> None:
    """Тест: удаление уже неактивного промпта"""
    test_prompt.is_active = False
    await db_session.commit()

    response = await client.delete(f"/api/v2/prompts/{test_prompt.id}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_prompt_other_user(
    client: AsyncClient,
    admin_headers: dict[str, str],
    test_prompt: PromptModel,
) -> None:
    """Тест: попытка удалить промпт другого пользователя"""
    response = await client.delete(f"/api/v2/prompts/{test_prompt.id}", headers=admin_headers)
    assert response.status_code == 404
