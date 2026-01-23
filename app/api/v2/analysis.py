from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.depends.db_depends import get_async_postgres_db
from app.models.users import User as UserModel
from app.models.vacancy_analysis import VacancyAnalysis as VacancyAnalysisModel
from app.schemas.vacancy_analysis import VacancyResponse


router = APIRouter(prefix="/analyses", tags=["Analyses_V2"])


@router.get("/{id_analysis}", status_code=status.HTTP_200_OK, summary="Получить анализ по ID")
async def get_analysis(
    id_analysis: UUID,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> VacancyResponse:
    """
    Возвращает анализ по его ID.
    """
    logger.info(f"Запрос на получение анализа {id_analysis} пользователя {current_user.id}")
    result = await db.scalars(
        select(VacancyAnalysisModel).where(
            VacancyAnalysisModel.id == id_analysis, VacancyAnalysisModel.user_id == current_user.id
        )
    )

    analysis = result.first()

    if not analysis:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")

    return VacancyResponse.model_validate(analysis)


@router.delete("/{id_analysis}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить анализ")
async def delete_analysis(
    id_analysis: UUID,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> None:
    """
    Удаляет анализ по ID.

    **Внимание:** Это действие необратимо!
    """
    logger.info(f"Запрос на удаление анализа {id_analysis} пользователем {current_user.id}")

    result = await db.scalars(
        select(VacancyAnalysisModel).where(
            VacancyAnalysisModel.id == id_analysis, VacancyAnalysisModel.user_id == current_user.id
        )
    )
    analysis = result.first()

    if not analysis:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")

    await db.delete(analysis)
    await db.commit()

    logger.info(f"Удалён анализ {id_analysis}")
