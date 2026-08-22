from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger

from app.application.exceptions.vacancy import AnalysisNotFoundError
from app.application.schemas.vacancy_analysis import VacancyResponse
from app.application.services.vacancy_analysis_service import VacancyAnalysisService
from app.domain.models.user import User as UserModel
from app.presentation.dependencies import get_current_user, get_vacancy_analysis_service


router = APIRouter(prefix="/analyses", tags=["Analyses_V1"])


@router.get("/{id_analysis}", status_code=status.HTTP_200_OK, summary="Получить анализ по ID")
async def get_analysis(
    id_analysis: UUID,
    current_user: UserModel = Depends(get_current_user),
    analysis_service: VacancyAnalysisService = Depends(get_vacancy_analysis_service),
) -> VacancyResponse:
    """
    Возвращает анализ по его ID.

    **Возможные ошибки:** `404` — анализ не найден или принадлежит другому пользователю.
    """
    logger.info(f"Запрос на получение анализа {id_analysis} пользователя {current_user.id}")

    try:
        analysis = await analysis_service.get_analysis(current_user.id, id_analysis)
    except AnalysisNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None

    return VacancyResponse.model_validate(analysis)


@router.delete("/{id_analysis}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить анализ")
async def delete_analysis(
    id_analysis: UUID,
    current_user: UserModel = Depends(get_current_user),
    analysis_service: VacancyAnalysisService = Depends(get_vacancy_analysis_service),
) -> None:
    """
    Удаляет анализ по ID.

    **Внимание:** Это действие необратимо!

    **Возможные ошибки:** `404` — анализ не найден или принадлежит другому пользователю.
    """
    logger.info(f"Запрос на удаление анализа {id_analysis} пользователем {current_user.id}")

    try:
        await analysis_service.delete_analysis(current_user.id, id_analysis)
    except AnalysisNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
