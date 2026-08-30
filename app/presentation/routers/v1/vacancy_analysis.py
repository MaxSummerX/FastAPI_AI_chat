from uuid import UUID

from fastapi import APIRouter, Depends, status
from loguru import logger

from app.application.schemas.vacancy_analysis import (
    AnalysisTypeInfo,
    AvailableAnalysesResponse,
    VacancyAnalysisCreate,
    VacancyBaseResponse,
    VacancyListResponse,
    VacancyResponse,
)
from app.application.services.vacancy_analysis_service import VacancyAnalysisService
from app.domain.enums.analysis import AnalysisType
from app.domain.models.user import User as UserModel
from app.presentation.dependencies import get_current_user, get_vacancy_analysis_service


router = APIRouter(prefix="/{id_vacancy}/analyses", tags=["Vacancy_analyses_V1"])


@router.get("", status_code=status.HTTP_200_OK, summary="Получить все анализы вакансии")
async def get_all_vacancy_analyses(
    id_vacancy: UUID,
    current_user: UserModel = Depends(get_current_user),
    analysis_service: VacancyAnalysisService = Depends(get_vacancy_analysis_service),
) -> VacancyListResponse:
    """
    Возвращает все анализы вакансии по id вакансии.

    **Возможные ошибки:** `404` — вакансия не найдена или принадлежит другому пользователю.
    """
    logger.info(f"Запрос на получение анализов вакансии {id_vacancy} пользователя {current_user.id}")

    analyses = await analysis_service.get_all_for_vacancy(current_user.id, id_vacancy)

    # Собираем уникальные типы анализов
    analyses_types = list({AnalysisType(analysis.analysis_type) for analysis in analyses})

    return VacancyListResponse(
        items=[VacancyBaseResponse.model_validate(analysis) for analysis in analyses], analyses_types=analyses_types
    )


@router.post("", status_code=status.HTTP_201_CREATED, summary="Создать анализ вакансии")
async def create_vacancy_analysis(
    id_vacancy: UUID,
    data: VacancyAnalysisCreate,
    current_user: UserModel = Depends(get_current_user),
    analysis_service: VacancyAnalysisService = Depends(get_vacancy_analysis_service),
) -> VacancyResponse:
    """
    Создает анализ вакансии по заданному типу.

    Для типа CUSTOM обязательно указать custom_prompt и title.
    Для системных типов title генерируется автоматически.

    Типы анализов:
    - matching: Анализ соответствия кандидата вакансии.
    - prioritization: Оценка привлекательности вакансии для отклика
    - preparation: Подготовка к собеседованию
    - skill_gap: Анализ пробелов в навыках
    - custom: Пользовательский промпт

    **Возможные ошибки:**
    - `400` — некорректный тип анализа / нет custom_prompt для CUSTOM
    - `404` — вакансия не найдена или принадлежит другому пользователю
    - `409` — анализ этого типа уже существует
    - `422` — резюме не загружено или слишком короткое
    - `503` — ошибка AI-сервиса
    """
    logger.info(f"Запрос на создание анализа {data.analysis_type} вакансии {id_vacancy}")

    analysis = await analysis_service.create_analysis(
        current_user.id,
        id_vacancy,
        analysis_type=data.analysis_type,
        custom_prompt=data.custom_prompt,
        title=data.title,
        resume=current_user.resume,
    )

    return VacancyResponse.model_validate(analysis)


@router.get("/types", status_code=status.HTTP_200_OK, summary="Получить доступные типы анализов")
async def get_available_analysis_types() -> AvailableAnalysesResponse:
    """
    Возвращает список всех доступных типов анализов вакансий.
    Используется для отображения опций в UI.
    """
    items = [
        AnalysisTypeInfo(
            value=analysis_type.value,
            display_name=analysis_type.display_name,
            description=analysis_type.description,
            is_builtin=analysis_type in AnalysisType.builtin_types(),
        )
        for analysis_type in AnalysisType
    ]

    return AvailableAnalysesResponse(items=items)
