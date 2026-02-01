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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enum.experience import Experience
from app.models.user_vacancies import UserVacancies
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
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_vacancy: VacancyModel,
    test_user: UserModel,
    db_session: AsyncSession,
) -> None:
    """Тест: добавление вакансии по hh_id из БД к пользователю"""
    # First, remove the existing UserVacancy link so we can test adding it back
    from app.models.user_vacancies import UserVacancies

    result = await db_session.scalars(
        select(UserVacancies).where(
            UserVacancies.user_id == test_user.id,
            UserVacancies.vacancy_id == test_vacancy.id,
        )
    )
    existing_link = result.one_or_none()
    if existing_link:
        await db_session.delete(existing_link)
        await db_session.commit()

    # POST request to add existing vacancy to user's pool
    response = await client.post(f"/api/v2/vacancies/head_hunter/{test_vacancy.hh_id}", headers=auth_headers)
    assert response.status_code == 204

    # Verify the link was created
    result = await db_session.scalars(
        select(UserVacancies).where(
            UserVacancies.user_id == test_user.id,
            UserVacancies.vacancy_id == test_vacancy.id,
        )
    )
    link = result.one_or_none()
    assert link is not None


@pytest.mark.asyncio
async def test_get_vacancy_by_hh_id_with_import(
    client: AsyncClient, auth_headers_import: dict[str, str], test_user: UserModel
) -> None:
    """Тест: импорт вакансии с hh.ru при отсутствии в БД (POST request)"""
    from datetime import UTC, datetime

    from app.models.vacancies import Vacancy

    hh_id = "99999999"

    # Мокаем функцию vacancy_create напрямую
    mock_vacancy = Vacancy(
        id=uuid.uuid4(),
        hh_id=hh_id,
        query_request="Personal request",
        title="Test Python Developer",
        description="Test description from HH.ru",
        salary_from=120000,
        salary_to=180000,
        salary_currency="RUR",
        salary_gross=True,
        experience_id="between1And3",
        area_id="1",
        area_name="Москва",
        schedule_id="fullDay",
        employment_id="full",
        employer_id="12345",
        employer_name="HH Company",
        hh_url=f"https://hh.ru/vacancy/{hh_id}",
        apply_url=f"https://hh.ru/vacancy/{hh_id}?apply=true",
        is_archived=False,
        published_at=datetime.now(UTC),
        is_active=True,
    )

    with patch("app.api.v2.vacancy.vacancy_create", new_callable=AsyncMock, return_value=mock_vacancy):
        # POST request to add vacancy to user's pool
        response = await client.post(f"/api/v2/vacancies/head_hunter/{hh_id}", headers=auth_headers_import)

        assert response.status_code == 204


@pytest.mark.asyncio
async def test_get_vacancy_by_hh_id_not_found_on_hh(client: AsyncClient, auth_headers_import: dict[str, str]) -> None:
    """Тест: вакансия не найдена на hh.ru"""
    from fastapi import HTTPException

    hh_id = "00000000"

    with patch("app.api.v2.vacancy.vacancy_create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = HTTPException(status_code=404, detail="Vacancy not found")

        response = await client.post(f"/api/v2/vacancies/head_hunter/{hh_id}", headers=auth_headers_import)

        assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_vacancy_by_hh_id_unauthorized(client: AsyncClient) -> None:
    """Тест: добавление вакансии по hh_id без авторизации"""
    response = await client.post("/api/v2/vacancies/head_hunter/12345678")
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
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_vacancy: VacancyModel,
    test_user: UserModel,
    db_session: AsyncSession,
) -> None:
    """Тест: успешное добавление вакансии в избранное"""
    # First set is_favorite to False
    result = await db_session.scalars(
        select(UserVacancies).where(
            UserVacancies.user_id == test_user.id,
            UserVacancies.vacancy_id == test_vacancy.id,
        )
    )
    link = result.one_or_none()
    if link:
        link.is_favorite = False
        await db_session.commit()

    response = await client.put(f"/api/v2/vacancies/{test_vacancy.id}/favorite", headers=auth_headers)
    assert response.status_code == 204

    # Проверяем, что вакансия помечена как избранная через UserVacancies
    await db_session.refresh(link)
    assert link.is_favorite is True


@pytest.mark.asyncio
async def test_add_to_favorites_already_favorite(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_vacancy: VacancyModel,
    test_user: UserModel,
    db_session: AsyncSession,
) -> None:
    """Тест: повторное добавление в избранное (idempotent)"""
    result = await db_session.scalars(
        select(UserVacancies).where(
            UserVacancies.user_id == test_user.id,
            UserVacancies.vacancy_id == test_vacancy.id,
        )
    )
    link = result.one_or_none()
    if link:
        link.is_favorite = True
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
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_vacancy: VacancyModel,
    test_user: UserModel,
    db_session: AsyncSession,
) -> None:
    """Тест: успешное удаление вакансии из избранного"""
    # First set is_favorite to True
    result = await db_session.scalars(
        select(UserVacancies).where(
            UserVacancies.user_id == test_user.id,
            UserVacancies.vacancy_id == test_vacancy.id,
        )
    )
    link = result.one_or_none()
    if link:
        link.is_favorite = True
        await db_session.commit()

    response = await client.delete(f"/api/v2/vacancies/{test_vacancy.id}/favorite", headers=auth_headers)
    assert response.status_code == 204

    # Проверяем, что вакансия помечена как не избранная через UserVacancies
    await db_session.refresh(link)
    assert link.is_favorite is False


@pytest.mark.asyncio
async def test_remove_from_favorites_not_favorite(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_vacancy: VacancyModel,
    test_user: UserModel,
    db_session: AsyncSession,
) -> None:
    """Тест: удаление из избранного вакансии, которая там не находится (idempotent)"""
    # First set is_favorite to False
    result = await db_session.scalars(
        select(UserVacancies).where(
            UserVacancies.user_id == test_user.id,
            UserVacancies.vacancy_id == test_vacancy.id,
        )
    )
    link = result.one_or_none()
    if link:
        link.is_favorite = False
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
