"""
Тесты для tasks endpoints API v2.

Покрывает все основные сценарии:
- Импорт вакансий с hh.ru в фоновом режиме через Celery
- Проверка статуса задач
- Анализ вакансий в фоновом режиме
"""

import pytest
from httpx import AsyncClient

from app.enum.experience import Experience


# ============================================================
# POST /tasks/import_vacancies - импорт вакансий в фоне
# ============================================================


@pytest.mark.asyncio
async def test_import_vacancies_success(
    client_with_mocked_import: AsyncClient, auth_headers_import: dict[str, str]
) -> None:
    """Тест: успешный запуск импорта вакансий в фоновом режиме"""
    response = await client_with_mocked_import.post(
        "/api/v2/tasks/import_vacancies",
        headers=auth_headers_import,
        params={"query": "python developer"},
    )

    assert response.status_code == 202
    data = response.json()
    assert "task_id" in data
    assert "status" in data
    assert "query" in data
    assert data["query"] == "python developer"


@pytest.mark.asyncio
async def test_import_vacancies_with_tiers(
    client_with_mocked_import: AsyncClient, auth_headers_import: dict[str, str]
) -> None:
    """Тест: импорт вакансий с фильтрацией по уровню опыта"""
    response = await client_with_mocked_import.post(
        "/api/v2/tasks/import_vacancies",
        headers=auth_headers_import,
        params={
            "query": "django developer",
            "tiers": [Experience.tier_1.value, Experience.tier_2.value],
        },
    )

    assert response.status_code == 202


@pytest.mark.asyncio
async def test_import_vacancies_unauthorized(client_with_mocked_import: AsyncClient) -> None:
    """Тест: запуск импорта без авторизации"""
    response = await client_with_mocked_import.post(
        "/api/v2/tasks/import_vacancies",
        params={"query": "python developer"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_import_vacancies_with_all_tiers(
    client_with_mocked_import: AsyncClient, auth_headers_import: dict[str, str]
) -> None:
    """Тест: импорт вакансий для всех уровней опыта"""
    response = await client_with_mocked_import.post(
        "/api/v2/tasks/import_vacancies",
        headers=auth_headers_import,
        params={"query": "fastapi developer"},
    )

    assert response.status_code == 202


# ============================================================
# GET /tasks/{task_id} - проверка статуса задачи
# ============================================================


@pytest.mark.asyncio
async def test_get_task_status_success(
    client_with_mocked_import: AsyncClient, auth_headers_import: dict[str, str]
) -> None:
    """Тест: успешная проверка статуса задачи"""
    # Сначала запускаем задачу
    import_response = await client_with_mocked_import.post(
        "/api/v2/tasks/import_vacancies",
        headers=auth_headers_import,
        params={"query": "test query"},
    )

    assert import_response.status_code == 202
    import_data = import_response.json()
    task_id = import_data["task_id"]

    # Проверяем статус
    response = await client_with_mocked_import.get(
        f"/api/v2/tasks/{task_id}",
        headers=auth_headers_import,
    )

    assert response.status_code == 200
    data = response.json()
    assert "task_id" in data
    assert data["task_id"] == task_id
    assert "status" in data


@pytest.mark.asyncio
async def test_get_task_status_unauthorized(client_with_mocked_import: AsyncClient) -> None:
    """Тест: проверка статуса без авторизации"""
    response = await client_with_mocked_import.get("/api/v2/tasks/some-task-id")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_task_status_not_found(
    client_with_mocked_import: AsyncClient, auth_headers_import: dict[str, str]
) -> None:
    """Тест: проверка статуса несуществующей задачи"""
    response = await client_with_mocked_import.get(
        "/api/v2/tasks/non-existent-task-id",
        headers=auth_headers_import,
    )

    # Статус 200 с PENDING для несуществующих задач (особенности Celery)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["PENDING", "FAILURE"]
