"""
Тесты для vacancy endpoints API v2.

Покрывает все основные сценарии:
- Получение вакансий с пагинацией
- Получение вакансии по UUID
- Получение вакансии по hh_id (с автоимпортом)
- Мягкое удаление вакансии
- Управление избранным (добавление/удаление)
- Импорт вакансий с hh.ru в фоновом режиме
- Фильтрация по уровню опыта и избранному
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.enum.experience import Experience
from app.models.users import User as UserModel
from app.models.vacancies import Vacancy as VacancyModel


# ============================================================
# GET /vacancies - получение вакансий с пагинацией
# ============================================================


@pytest.mark.asyncio
async def test_get_vacancies_unauthorized(client: AsyncClient) -> None:
    """Тест: неавторизованный запрос к /vacancies"""
    response = await client.get("/api/v2/vacancies")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_vacancies_first_page(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancies: list[VacancyModel]
) -> None:
    """Тест: получение первой страницы вакансий (без курсора)"""
    response = await client.get("/api/v2/vacancies", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert "next_cursor" in data
    assert "has_next" in data

    # Должно вернуть 20 вакансий (default limit)
    assert len(data["items"]) == 20
    assert data["has_next"] is True  # Ещё есть 10 вакансий
    assert data["next_cursor"] is not None


@pytest.mark.asyncio
async def test_get_vacancies_with_custom_limit(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancies: list[VacancyModel]
) -> None:
    """Тест: получение вакансий с кастомным limit"""
    response = await client.get("/api/v2/vacancies", headers=auth_headers, params={"limit": 10})
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) == 10
    assert data["has_next"] is True


@pytest.mark.asyncio
async def test_get_vacancies_with_cursor(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancies: list[VacancyModel]
) -> None:
    """Тест: получение второй страницы с курсором"""
    # Первая страница
    first_response = await client.get("/api/v2/vacancies", headers=auth_headers, params={"limit": 10})
    first_data = first_response.json()
    cursor = first_data["next_cursor"]

    # Проверяем что курсор не пустой
    assert cursor is not None

    # Вторая страница с курсором
    response = await client.get("/api/v2/vacancies", headers=auth_headers, params={"limit": 10, "cursor": cursor})
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) == 10
    # Вакансии должны отличаться от первой страницы
    first_ids = {item["id"] for item in first_data["items"]}
    second_ids = {item["id"] for item in data["items"]}
    assert len(first_ids.intersection(second_ids)) == 0


@pytest.mark.asyncio
async def test_get_vacancies_last_page(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancies: list[VacancyModel]
) -> None:
    """Тест: получение последней страницы"""
    # Запрашиваем больше чем есть
    response = await client.get("/api/v2/vacancies", headers=auth_headers, params={"limit": 50})
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) == 30
    assert data["has_next"] is False
    assert data["next_cursor"] is None


@pytest.mark.asyncio
async def test_get_vacancies_invalid_cursor(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: получение с невалидным курсором"""
    response = await client.get("/api/v2/vacancies", headers=auth_headers, params={"cursor": "invalid_cursor"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_vacancies_limit_validation(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: валидация limit параметра"""
    # Слишком большой limit - должен использовать максимальное значение (100)
    response = await client.get("/api/v2/vacancies", headers=auth_headers, params={"limit": 150})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_vacancies_empty_db(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: получение вакансий из пустой БД"""
    response = await client.get("/api/v2/vacancies", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) == 0
    assert data["has_next"] is False
    assert data["next_cursor"] is None


@pytest.mark.asyncio
async def test_get_vacancies_filter_by_favorite(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancies: list[VacancyModel]
) -> None:
    """Тест: фильтрация вакансий по избранному"""
    # Получаем только избранные
    response = await client.get("/api/v2/vacancies", headers=auth_headers, params={"favorite": True})
    assert response.status_code == 200

    data = response.json()
    # Все вакансии должны быть в избранном
    for item in data["items"]:
        assert item["is_favorite"] is True


@pytest.mark.asyncio
async def test_get_vacancies_exclude_favorite(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancies: list[VacancyModel]
) -> None:
    """Тест: исключение избранных вакансий"""
    # Получаем всё кроме избранных
    response = await client.get("/api/v2/vacancies", headers=auth_headers, params={"favorite": False})
    assert response.status_code == 200

    data = response.json()
    # Никакая вакансия не должна быть в избранном
    for item in data["items"]:
        assert item["is_favorite"] is False


@pytest.mark.asyncio
async def test_get_vacancies_filter_by_tier(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancies: list[VacancyModel]
) -> None:
    """Тест: фильтрация вакансий по уровню опыта"""
    # Фильтр по одному уровню опыта
    response = await client.get(
        "/api/v2/vacancies",
        headers=auth_headers,
        params={"tier": Experience.tier_0.value},
    )
    assert response.status_code == 200

    data = response.json()
    # Все вакансии должны иметь указанный уровень опыта
    for item in data["items"]:
        assert item["experience_id"] == Experience.tier_0.value


@pytest.mark.asyncio
async def test_get_vacancies_filter_by_multiple_tiers(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancies: list[VacancyModel]
) -> None:
    """Тест: фильтрация вакансий по нескольким уровням опыта"""
    # Фильтр по нескольким уровням опыта
    response = await client.get(
        "/api/v2/vacancies",
        headers=auth_headers,
        params={
            "tier": [
                Experience.tier_0.value,
                Experience.tier_1.value,
            ]
        },
    )
    assert response.status_code == 200

    data = response.json()
    # Все вакансии должны иметь один из указанных уровней опыта
    for item in data["items"]:
        assert item["experience_id"] in [Experience.tier_0.value, Experience.tier_1.value]


# ============================================================
# GET /vacancies/{id} - получение вакансии по UUID
# ============================================================


@pytest.mark.asyncio
async def test_get_vacancy_by_id_success(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancy: VacancyModel
) -> None:
    """Тест: успешное получение вакансии по UUID"""
    response = await client.get(f"/api/v2/vacancies/{test_vacancy.id}", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(test_vacancy.id)
    assert data["hh_id"] == test_vacancy.hh_id
    assert data["title"] == test_vacancy.title
    assert "description" in data
    assert "salary_from" in data
    assert "salary_to" in data


@pytest.mark.asyncio
async def test_get_vacancy_by_id_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: попытка получить несуществующую вакансию"""
    response = await client.get(f"/api/v2/vacancies/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_vacancy_by_id_unauthorized(client: AsyncClient, test_vacancy: VacancyModel) -> None:
    """Тест: получение вакансии без авторизации"""
    response = await client.get(f"/api/v2/vacancies/{test_vacancy.id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_vacancy_by_id_inactive(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancy: VacancyModel, db_session: AsyncSession
) -> None:
    """Тест: попытка получить неактивную вакансию"""
    # Делаем вакансию неактивной
    test_vacancy.is_active = False
    await db_session.commit()

    response = await client.get(f"/api/v2/vacancies/{test_vacancy.id}", headers=auth_headers)
    assert response.status_code == 404


# ============================================================
# GET /vacancies/head_hunter/{hh_id} - получение вакансии по hh_id
# ============================================================


@pytest.mark.asyncio
async def test_get_vacancy_by_hh_id_from_db(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancy: VacancyModel
) -> None:
    """Тест: получение вакансии по hh_id из БД (без импорта)"""
    response = await client.get(f"/api/v2/vacancies/head_hunter/{test_vacancy.hh_id}", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["hh_id"] == test_vacancy.hh_id
    assert data["title"] == test_vacancy.title


@pytest.mark.asyncio
async def test_get_vacancy_by_hh_id_with_import(
    client: AsyncClient, auth_headers: dict[str, str], test_user: UserModel
) -> None:
    """Тест: импорт вакансии с hh.ru при отсутствии в БД"""
    hh_id = "99999999"

    # Мокаем функцию vacancy_create для избежания реального HTTP запроса
    mock_vacancy_data = {
        "id": hh_id,
        "name": "Test Python Developer",
        "description": "Test description from HH.ru",
        "salary": {"from": 120000, "to": 180000, "currency": "RUR", "gross": True},
        "experience": {"id": "between1And3"},
        "area": {"id": "1", "name": "Москва"},
        "schedule": {"id": "fullDay"},
        "employment": {"id": "full"},
        "employer": {"id": "12345", "name": "HH Company"},
        "alternate_url": f"https://hh.ru/vacancy/{hh_id}",
        "apply_alternate_url": f"https://hh.ru/vacancy/{hh_id}?apply=true",
        "archived": False,
        "published_at": "2026-01-15T12:00:00+0300",
    }

    with patch("app.tools.headhunter.find_vacancies.fetch_full_vacancy", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_vacancy_data

        response = await client.get(f"/api/v2/vacancies/head_hunter/{hh_id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["hh_id"] == hh_id
        assert data["title"] == "Test Python Developer"
        mock_fetch.assert_called_once_with(hh_id)


@pytest.mark.asyncio
async def test_get_vacancy_by_hh_id_not_found_on_hh(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: вакансия не найдена на hh.ru"""
    hh_id = "00000000"

    with patch(
        "app.tools.headhunter.find_vacancies.fetch_full_vacancy",
        new_callable=AsyncMock,
    ) as mock_fetch:
        from fastapi import HTTPException

        mock_fetch.side_effect = HTTPException(status_code=404, detail="Vacancy not found")

        response = await client.get(f"/api/v2/vacancies/head_hunter/{hh_id}", headers=auth_headers)

        assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_vacancy_by_hh_id_unauthorized(client: AsyncClient) -> None:
    """Тест: получение вакансии по hh_id без авторизации"""
    response = await client.get("/api/v2/vacancies/head_hunter/12345678")
    assert response.status_code == 401


# ============================================================
# DELETE /vacancies/{id} - мягкое удаление вакансии
# ============================================================


@pytest.mark.asyncio
async def test_delete_vacancy_success(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancy: VacancyModel, db_session: AsyncSession
) -> None:
    """Тест: успешное мягкое удаление вакансии"""
    response = await client.delete(f"/api/v2/vacancies/{test_vacancy.id}", headers=auth_headers)
    assert response.status_code == 204

    # Проверяем, что вакансия помечена как неактивная
    await db_session.refresh(test_vacancy)
    assert test_vacancy.is_active is False


@pytest.mark.asyncio
async def test_delete_vacancy_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: удаление несуществующей вакансии"""
    response = await client.delete(f"/api/v2/vacancies/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_vacancy_unauthorized(client: AsyncClient, test_vacancy: VacancyModel) -> None:
    """Тест: удаление вакансии без авторизации"""
    response = await client.delete(f"/api/v2/vacancies/{test_vacancy.id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_other_user_vacancy(
    client: AsyncClient, admin_headers: dict[str, str], test_vacancy: VacancyModel
) -> None:
    """Тест: попытка удалить вакансию другого пользователя"""
    # test_vacancy принадлежит test_user, а запрашивает admin
    response = await client.delete(f"/api/v2/vacancies/{test_vacancy.id}", headers=admin_headers)
    assert response.status_code == 404


# ============================================================
# PUT /vacancies/{id}/favorite - добавление в избранное
# ============================================================


@pytest.mark.asyncio
async def test_add_to_favorites_success(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancy: VacancyModel, db_session: AsyncSession
) -> None:
    """Тест: успешное добавление вакансии в избранное"""
    response = await client.put(f"/api/v2/vacancies/{test_vacancy.id}/favorite", headers=auth_headers)
    assert response.status_code == 204

    # Проверяем, что вакансия помечена как избранная
    await db_session.refresh(test_vacancy)
    assert test_vacancy.is_favorite is True


@pytest.mark.asyncio
async def test_add_to_favorites_already_favorite(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancy: VacancyModel, db_session: AsyncSession
) -> None:
    """Тест: повторное добавление в избранное (idempotent)"""
    test_vacancy.is_favorite = True
    await db_session.commit()

    response = await client.put(f"/api/v2/vacancies/{test_vacancy.id}/favorite", headers=auth_headers)
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_add_to_favorites_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: добавление в избранное несуществующей вакансии"""
    response = await client.put(f"/api/v2/vacancies/{uuid.uuid4()}/favorite", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_add_to_favorites_unauthorized(client: AsyncClient, test_vacancy: VacancyModel) -> None:
    """Тест: добавление в избранное без авторизации"""
    response = await client.put(f"/api/v2/vacancies/{test_vacancy.id}/favorite")
    assert response.status_code == 401


# ============================================================
# DELETE /vacancies/{id}/favorite - удаление из избранного
# ============================================================


@pytest.mark.asyncio
async def test_remove_from_favorites_success(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancy: VacancyModel, db_session: AsyncSession
) -> None:
    """Тест: успешное удаление вакансии из избранного"""
    test_vacancy.is_favorite = True
    await db_session.commit()

    response = await client.delete(f"/api/v2/vacancies/{test_vacancy.id}/favorite", headers=auth_headers)
    assert response.status_code == 204

    # Проверяем, что вакансия помечена как не избранная
    await db_session.refresh(test_vacancy)
    assert test_vacancy.is_favorite is False


@pytest.mark.asyncio
async def test_remove_from_favorites_not_favorite(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancy: VacancyModel, db_session: AsyncSession
) -> None:
    """Тест: удаление из избранного вакансии, которая там не находится (idempotent)"""
    test_vacancy.is_favorite = False
    await db_session.commit()

    response = await client.delete(f"/api/v2/vacancies/{test_vacancy.id}/favorite", headers=auth_headers)
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_remove_from_favorites_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: удаление из избранного несуществующей вакансии"""
    response = await client.delete(f"/api/v2/vacancies/{uuid.uuid4()}/favorite", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_remove_from_favorites_unauthorized(client: AsyncClient, test_vacancy: VacancyModel) -> None:
    """Тест: удаление из избранного без авторизации"""
    response = await client.delete(f"/api/v2/vacancies/{test_vacancy.id}/favorite")
    assert response.status_code == 401


# ============================================================
# POST /vacancies/import_vacancies - импорт в фоновом режиме
# ============================================================


@pytest.mark.asyncio
async def test_import_vacancies_success(
    client_with_mocked_import: AsyncClient, auth_headers_import: dict[str, str]
) -> None:
    """Тест: успешный запуск импорта вакансий в фоновом режиме"""
    response = await client_with_mocked_import.post(
        "/api/v2/vacancies/import_vacancies",
        headers=auth_headers_import,
        params={"query": "python developer"},
    )

    assert response.status_code == 202
    data = response.json()
    assert "message" in data
    assert "python developer" in data["message"]


@pytest.mark.asyncio
async def test_import_vacancies_with_tiers(
    client_with_mocked_import: AsyncClient, auth_headers_import: dict[str, str]
) -> None:
    """Тест: импорт вакансий с фильтрацией по уровню опыта"""
    response = await client_with_mocked_import.post(
        "/api/v2/vacancies/import_vacancies",
        headers=auth_headers_import,
        params={
            "query": "django developer",
            "tier": [Experience.tier_1.value, Experience.tier_2.value],
        },
    )

    assert response.status_code == 202


@pytest.mark.asyncio
async def test_import_vacancies_unauthorized(client_with_mocked_import: AsyncClient) -> None:
    """Тест: запуск импорта без авторизации"""
    response = await client_with_mocked_import.post(
        "/api/v2/vacancies/import_vacancies",
        params={"query": "python developer"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_import_vacancies_with_all_tiers(
    client_with_mocked_import: AsyncClient, auth_headers_import: dict[str, str]
) -> None:
    """Тест: импорт вакансий для всех уровней опыта"""
    response = await client_with_mocked_import.post(
        "/api/v2/vacancies/import_vacancies",
        headers=auth_headers_import,
        params={"query": "fastapi developer"},
    )

    assert response.status_code == 202
