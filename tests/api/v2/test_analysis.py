"""
Тесты для analysis endpoints API v2.

Покрывает все основные сценарии:
- Получение анализа по ID
- Удаление анализа
- Обработка ошибок (анализ не найден, чужой анализ, неавторизованный доступ)
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vacancy_analysis import VacancyAnalysis as VacancyAnalysisModel


# ============================================================
# GET /analyses/{id_analysis} - получение анализа по ID
# ============================================================


@pytest.mark.asyncio
async def test_get_analysis_unauthorized(client: AsyncClient, test_vacancy_analysis: VacancyAnalysisModel) -> None:
    """Тест: неавторизованный запрос к /analyses/{id_analysis}"""
    response = await client.get(f"/api/v2/analyses/{test_vacancy_analysis.id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_analysis_success(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancy_analysis: VacancyAnalysisModel
) -> None:
    """Тест: успешное получение анализа по ID"""
    response = await client.get(f"/api/v2/analyses/{test_vacancy_analysis.id}", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(test_vacancy_analysis.id)
    assert data["vacancy_id"] == str(test_vacancy_analysis.vacancy_id)
    assert data["title"] == test_vacancy_analysis.title
    assert data["analysis_type"] == test_vacancy_analysis.analysis_type


@pytest.mark.asyncio
async def test_get_analysis_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: попытка получить несуществующий анализ"""
    response = await client.get(f"/api/v2/analyses/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_analysis_other_user(
    client: AsyncClient, admin_headers: dict[str, str], test_vacancy_analysis: VacancyAnalysisModel
) -> None:
    """Тест: попытка получить анализ другого пользователя"""
    response = await client.get(f"/api/v2/analyses/{test_vacancy_analysis.id}", headers=admin_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_analysis_response_structure(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancy_analysis: VacancyAnalysisModel
) -> None:
    """Тест: проверка структуры ответа для получения анализа"""
    response = await client.get(f"/api/v2/analyses/{test_vacancy_analysis.id}", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    # Проверяем наличие всех полей VacancyResponse
    assert "id" in data
    assert "vacancy_id" in data
    assert "title" in data
    assert "analysis_type" in data
    assert "prompt_template" in data
    assert "custom_prompt" in data
    assert "result_data" in data
    assert "result_text" in data
    assert "model_used" in data
    assert "tokens_used" in data
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_get_analysis_all_fields(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancy_analysis: VacancyAnalysisModel
) -> None:
    """Тест: проверка что все поля корректно возвращаются"""
    response = await client.get(f"/api/v2/analyses/{test_vacancy_analysis.id}", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["result_text"] == test_vacancy_analysis.result_text
    assert data["prompt_template"] == test_vacancy_analysis.prompt_template
    assert data["model_used"] == test_vacancy_analysis.model_used
    assert data["tokens_used"] == test_vacancy_analysis.tokens_used


# ============================================================
# DELETE /analyses/{id_analysis} - удаление анализа
# ============================================================


@pytest.mark.asyncio
async def test_delete_analysis_unauthorized(client: AsyncClient, test_vacancy_analysis: VacancyAnalysisModel) -> None:
    """Тест: удаление анализа без авторизации"""
    response = await client.delete(f"/api/v2/analyses/{test_vacancy_analysis.id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_analysis_success(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_vacancy_analysis: VacancyAnalysisModel,
) -> None:
    """Тест: успешное удаление анализа"""
    analysis_id = test_vacancy_analysis.id

    response = await client.delete(f"/api/v2/analyses/{analysis_id}", headers=auth_headers)
    assert response.status_code == 204

    # Проверяем что анализ действительно удалён
    from app.models.vacancy_analysis import VacancyAnalysis

    result = await db_session.scalars(select(VacancyAnalysis).where(VacancyAnalysis.id == analysis_id))
    analysis = result.first()
    assert analysis is None


@pytest.mark.asyncio
async def test_delete_analysis_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: попытка удалить несуществующий анализ"""
    response = await client.delete(f"/api/v2/analyses/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_analysis_other_user(
    client: AsyncClient, admin_headers: dict[str, str], test_vacancy_analysis: VacancyAnalysisModel
) -> None:
    """Тест: попытка удалить анализ другого пользователя"""
    response = await client.delete(f"/api/v2/analyses/{test_vacancy_analysis.id}", headers=admin_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_analysis_idempotent(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_vacancy_analysis: VacancyAnalysisModel,
) -> None:
    """Тест: повторное удаление анализа (должно вернуть 404)"""
    analysis_id = test_vacancy_analysis.id

    # Первое удаление
    response1 = await client.delete(f"/api/v2/analyses/{analysis_id}", headers=auth_headers)
    assert response1.status_code == 204

    # Второе удаление - должно вернуть 404
    response2 = await client.delete(f"/api/v2/analyses/{analysis_id}", headers=auth_headers)
    assert response2.status_code == 404


@pytest.mark.asyncio
async def test_delete_analysis_returns_no_content(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancy_analysis: VacancyAnalysisModel
) -> None:
    """Тест: удаление возвращает 204 No Content без тела ответа"""
    response = await client.delete(f"/api/v2/analyses/{test_vacancy_analysis.id}", headers=auth_headers)
    assert response.status_code == 204
    assert response.content == b""


# ============================================================
# Интеграционные тесты с несколькими анализами
# ============================================================


@pytest.mark.asyncio
async def test_get_and_delete_workflow(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancy_analyses: list[VacancyAnalysisModel]
) -> None:
    """Тест: полный цикл получения и удаления анализов"""
    # Получаем все анализы
    analyses = test_vacancy_analyses

    # Получаем каждый анализ по ID
    for analysis in analyses:
        response = await client.get(f"/api/v2/analyses/{analysis.id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(analysis.id)

    # Удаляем первый анализ
    first_analysis = analyses[0]
    response = await client.delete(f"/api/v2/analyses/{first_analysis.id}", headers=auth_headers)
    assert response.status_code == 204

    # Проверяем что удалённый анализ больше не доступен
    response = await client.get(f"/api/v2/analyses/{first_analysis.id}", headers=auth_headers)
    assert response.status_code == 404

    # Проверяем что другие анализы всё ещё доступны
    for analysis in analyses[1:]:
        response = await client.get(f"/api/v2/analyses/{analysis.id}", headers=auth_headers)
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_different_analysis_types(
    client: AsyncClient, auth_headers: dict[str, str], test_vacancy_analyses: list[VacancyAnalysisModel]
) -> None:
    """Тест: получение анализов разных типов"""
    from app.enum.analysis import AnalysisType

    for analysis in test_vacancy_analyses:
        response = await client.get(f"/api/v2/analyses/{analysis.id}", headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        # Проверяем что тип анализа корректен
        assert data["analysis_type"] in [t.value for t in AnalysisType]
        assert data["title"] is not None
        assert len(data["title"]) > 0
