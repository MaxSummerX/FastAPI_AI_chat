"""
Тесты для vacancy_analysis endpoints API v2.

Покрывает все основные сценарии:
- Получение всех анализов вакансии
- Создание нового анализа (встроенные типы и custom)
- Получение доступных типов анализов
- Обработка ошибок (вакансия не найдена, анализ уже существует, ошибки LLM)
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.enum.analysis import AnalysisType
from app.models.vacancies import Vacancy as VacancyModel
from app.models.vacancy_analysis import VacancyAnalysis as VacancyAnalysisModel


# ============================================================
# GET /{id_vacancy}/analyses - получение всех анализов вакансии
# ============================================================


@pytest.mark.asyncio
async def test_get_all_analyses_unauthorized(client: AsyncClient, test_vacancy: VacancyModel) -> None:
    """Тест: неавторизованный запрос к /{id_vacancy}/analyses"""
    response = await client.get(f"/api/v2/vacancies/{test_vacancy.id}/analyses")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_all_analyses_success(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancy_analyses: list[VacancyAnalysisModel]
) -> None:
    """Тест: успешное получение всех анализов вакансии"""
    vacancy_id = test_vacancy_analyses[0].vacancy_id
    response = await client.get(f"/api/v2/vacancies/{vacancy_id}/analyses", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert "analyses_types" in data

    # Все 5 типов анализов должны быть созданы
    assert len(data["items"]) == 5
    assert len(data["analyses_types"]) == 5


@pytest.mark.asyncio
async def test_get_all_analyses_empty(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancy: VacancyModel
) -> None:
    """Тест: получение анализов для вакансии без анализов"""
    response = await client.get(f"/api/v2/vacancies/{test_vacancy.id}/analyses", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) == 0
    assert len(data["analyses_types"]) == 0


@pytest.mark.asyncio
async def test_get_all_analyses_vacancy_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: попытка получить анализы для несуществующей вакансии"""
    response = await client.get(f"/api/v2/vacancies/{uuid.uuid4()}/analyses", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_all_analyses_inactive_vacancy(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancy: VacancyModel, db_session: AsyncSession
) -> None:
    """Тест: попытка получить анализы для неактивной вакансии"""
    test_vacancy.is_active = False
    await db_session.commit()

    response = await client.get(f"/api/v2/vacancies/{test_vacancy.id}/analyses", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_all_analyses_other_user_vacancy(
    client: AsyncClient, admin_headers: dict[str, str], test_vacancy_analyses: list[VacancyAnalysisModel]
) -> None:
    """Тест: попытка получить анализы вакансии другого пользователя"""
    vacancy_id = test_vacancy_analyses[0].vacancy_id
    response = await client.get(f"/api/v2/vacancies/{vacancy_id}/analyses", headers=admin_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_all_analyses_structure(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancy_analysis: VacancyAnalysisModel
) -> None:
    """Тест: проверка структуры ответа для списка анализов"""
    response = await client.get(f"/api/v2/vacancies/{test_vacancy_analysis.vacancy_id}/analyses", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    item = data["items"][0]

    # Проверяем наличие обязательных полей
    assert "id" in item
    assert "vacancy_id" in item
    assert "title" in item
    assert "analysis_type" in item
    assert "created_at" in item


@pytest.mark.asyncio
async def test_get_all_analyses_unique_types(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancy_analyses: list[VacancyAnalysisModel]
) -> None:
    """Тест: проверка что analyses_types содержат только уникальные типы"""
    vacancy_id = test_vacancy_analyses[0].vacancy_id
    response = await client.get(f"/api/v2/vacancies/{vacancy_id}/analyses", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    # Проверяем что все типы уникальны
    assert len(data["analyses_types"]) == len(set(data["analyses_types"]))


# ============================================================
# POST /{id_vacancy}/analyses - создание нового анализа
# ============================================================


@pytest.mark.asyncio
async def test_create_analysis_unauthorized(client: AsyncClient, test_vacancy: VacancyModel) -> None:
    """Тест: создание анализа без авторизации"""
    response = await client.post(
        f"/api/v2/vacancies/{test_vacancy.id}/analyses",
        json={"analysis_type": AnalysisType.MATCHING.value},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_analysis_builtin_type(
    client_with_mocked_llm: AsyncClient, auth_headers_llm: dict[str, str], test_vacancy: VacancyModel
) -> None:
    """Тест: успешное создание анализа встроенного типа"""
    response = await client_with_mocked_llm.post(
        f"/api/v2/vacancies/{test_vacancy.id}/analyses",
        headers=auth_headers_llm,
        json={"analysis_type": AnalysisType.MATCHING.value},
    )
    assert response.status_code == 201

    data = response.json()
    assert data["analysis_type"] == AnalysisType.MATCHING.value
    assert data["title"] == AnalysisType.MATCHING.display_name
    assert data["vacancy_id"] == str(test_vacancy.id)


@pytest.mark.asyncio
async def test_create_analysis_custom_success(
    client_with_mocked_llm: AsyncClient, auth_headers_llm: dict[str, str], test_vacancy: VacancyModel
) -> None:
    """Тест: успешное создание custom анализа с обязательными полями"""
    response = await client_with_mocked_llm.post(
        f"/api/v2/vacancies/{test_vacancy.id}/analyses",
        headers=auth_headers_llm,
        json={
            "analysis_type": AnalysisType.CUSTOM.value,
            "title": "Мой кастомный анализ",
            "custom_prompt": "Проанализируй эту вакансию с точки зрения...",
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert data["analysis_type"] == AnalysisType.CUSTOM.value
    assert data["title"] == "Мой кастомный анализ"
    assert data["custom_prompt"] == "Проанализируй эту вакансию с точки зрения..."


@pytest.mark.asyncio
async def test_create_analysis_custom_missing_prompt(
    client_with_mocked_llm: AsyncClient, auth_headers_llm: dict[str, str], test_vacancy: VacancyModel
) -> None:
    """Тест: custom анализ без обязательного custom_prompt"""
    response = await client_with_mocked_llm.post(
        f"/api/v2/vacancies/{test_vacancy.id}/analyses",
        headers=auth_headers_llm,
        json={"analysis_type": AnalysisType.CUSTOM.value, "title": "Test"},
    )
    assert response.status_code == 400
    assert "custom_prompt is required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_analysis_custom_missing_title(
    client_with_mocked_llm: AsyncClient, auth_headers_llm: dict[str, str], test_vacancy: VacancyModel
) -> None:
    """Тест: custom анализ без обязательного title"""
    response = await client_with_mocked_llm.post(
        f"/api/v2/vacancies/{test_vacancy.id}/analyses",
        headers=auth_headers_llm,
        json={"analysis_type": AnalysisType.CUSTOM.value, "custom_prompt": "Test prompt"},
    )
    assert response.status_code == 400
    assert "title is required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_analysis_already_exists(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancy_analysis: VacancyAnalysisModel
) -> None:
    """Тест: попытка создать анализ, который уже существует"""
    response = await client.post(
        f"/api/v2/vacancies/{test_vacancy_analysis.vacancy_id}/analyses",
        headers=auth_headers,
        json={"analysis_type": AnalysisType.MATCHING.value},
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_analysis_vacancy_not_found(
    client_with_mocked_llm: AsyncClient, auth_headers_llm: dict[str, str]
) -> None:
    """Тест: создание анализа для несуществующей вакансии"""
    response = await client_with_mocked_llm.post(
        f"/api/v2/vacancies/{uuid.uuid4()}/analyses",
        headers=auth_headers_llm,
        json={"analysis_type": AnalysisType.MATCHING.value},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_analysis_all_builtin_types(
    client_with_mocked_llm: AsyncClient, auth_headers_llm: dict[str, str], test_vacancy: VacancyModel
) -> None:
    """Тест: создание анализов всех встроенных типов"""
    builtin_types = AnalysisType.builtin_types()

    for analysis_type in builtin_types:
        response = await client_with_mocked_llm.post(
            f"/api/v2/vacancies/{test_vacancy.id}/analyses",
            headers=auth_headers_llm,
            json={"analysis_type": analysis_type.value},
        )
        assert response.status_code == 201, f"Failed for {analysis_type.value}"
        assert response.json()["title"] == analysis_type.display_name


@pytest.mark.asyncio
async def test_create_analysis_response_structure(
    client_with_mocked_llm: AsyncClient, auth_headers_llm: dict[str, str], test_vacancy: VacancyModel
) -> None:
    """Тест: проверка структуры ответа при создании анализа"""
    response = await client_with_mocked_llm.post(
        f"/api/v2/vacancies/{test_vacancy.id}/analyses",
        headers=auth_headers_llm,
        json={"analysis_type": AnalysisType.PRIORITIZATION.value},
    )
    assert response.status_code == 201

    data = response.json()
    # Проверяем наличие всех полей VacancyResponse
    assert "id" in data
    assert "vacancy_id" in data
    assert "title" in data
    assert "analysis_type" in data
    assert "prompt_template" in data
    assert "custom_prompt" in data
    assert "result_text" in data
    assert "created_at" in data
    assert "updated_at" in data


# ============================================================
# GET /{id_vacancy}/analyses/types - получение доступных типов
# ============================================================


@pytest.mark.asyncio
async def test_get_available_types_unauthorized(client: AsyncClient) -> None:
    """Тест: получение типов анализа без авторизации (должно работать)"""
    response = await client.get("/api/v2/vacancies/00000000-0000-0000-0000-000000000000/analyses/types")
    # Endpoint доступен без авторизации
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_available_types_success(client: AsyncClient) -> None:
    """Тест: успешное получение доступных типов анализов"""
    response = await client.get("/api/v2/vacancies/00000000-0000-0000-0000-000000000000/analyses/types")
    assert response.status_code == 200

    data = response.json()
    assert "items" in data

    items = data["items"]
    # Должны быть все 5 типов
    assert len(items) == 5

    # Проверяем структуру каждого типа
    for item in items:
        assert "value" in item
        assert "display_name" in item
        assert "description" in item
        assert "is_builtin" in item


@pytest.mark.asyncio
async def test_get_available_types_content(client: AsyncClient) -> None:
    """Тест: проверка содержимого доступных типов"""
    response = await client.get("/api/v2/vacancies/00000000-0000-0000-0000-000000000000/analyses/types")
    assert response.status_code == 200

    data = response.json()
    items = data["items"]

    # Проверяем встроенные типы
    builtin_items = [item for item in items if item["is_builtin"]]
    assert len(builtin_items) == 4  # matching, prioritization, preparation, skill_gap

    # Проверяем custom тип
    custom_item = next(item for item in items if item["value"] == AnalysisType.CUSTOM.value)
    assert custom_item["is_builtin"] is False
    assert custom_item["display_name"] == "Кастомный анализ"


@pytest.mark.asyncio
async def test_get_available_types_all_types_present(client: AsyncClient) -> None:
    """Тест: проверка что все типы из enum присутствуют в ответе"""
    response = await client.get("/api/v2/vacancies/00000000-0000-0000-0000-000000000000/analyses/types")
    assert response.status_code == 200

    data = response.json()
    items = data["items"]
    values = {item["value"] for item in items}

    # Проверяем что все типы из enum присутствуют
    for analysis_type in AnalysisType:
        assert analysis_type.value in values


# ============================================================
# Тесты с разными типами встроенных анализов
# ============================================================


@pytest.mark.asyncio
async def test_create_prioritization_analysis(
    client_with_mocked_llm: AsyncClient, auth_headers_llm: dict[str, str], test_vacancy: VacancyModel
) -> None:
    """Тест: создание анализа prioritization"""
    response = await client_with_mocked_llm.post(
        f"/api/v2/vacancies/{test_vacancy.id}/analyses",
        headers=auth_headers_llm,
        json={"analysis_type": AnalysisType.PRIORITIZATION.value},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Оценка привлекательности"


@pytest.mark.asyncio
async def test_create_preparation_analysis(
    client_with_mocked_llm: AsyncClient, auth_headers_llm: dict[str, str], test_vacancy: VacancyModel
) -> None:
    """Тест: создание анализа preparation"""
    response = await client_with_mocked_llm.post(
        f"/api/v2/vacancies/{test_vacancy.id}/analyses",
        headers=auth_headers_llm,
        json={"analysis_type": AnalysisType.PREPARATION.value},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Подготовка к интервью"


@pytest.mark.asyncio
async def test_create_skill_gap_analysis(
    client_with_mocked_llm: AsyncClient, auth_headers_llm: dict[str, str], test_vacancy: VacancyModel
) -> None:
    """Тест: создание анализа skill_gap"""
    response = await client_with_mocked_llm.post(
        f"/api/v2/vacancies/{test_vacancy.id}/analyses",
        headers=auth_headers_llm,
        json={"analysis_type": AnalysisType.SKILL_GAP.value},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Анализ навыков"
