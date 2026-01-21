from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.depends.db_depends import get_async_postgres_db
from app.models.users import User as UserModel
from app.tools.ai_research.ai_scan import analyze_vacancy_from_db


router = APIRouter(prefix="/", tags=["AI_analyses_V2"])


@router.post("/analyses", status_code=status.HTTP_201_CREATED)
async def create_vacancy_analysis() -> None:
    """
    Принимаем id вакансии и выбираем какие типы анализов нужно сделать.
    Создает анализ вакансии по заданному типа или по всем типам сразу.
    """
    pass


@router.get("/analyses", status_code=status.HTTP_200_OK)
async def get_all_vacancy_analyses() -> None:
    """
    возращаем все анализы вакансии по id вакансии, которые сделаны, иначе None
    """
    pass


@router.get("/analyses/{id}", status_code=status.HTTP_200_OK)
async def get_vacancy_analysis() -> None:
    """
    возвращаем анализ по её id
    """
    pass


@router.delete("/analyses/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vacancy_analysis() -> None:
    """
    Удаляем анализ по её id
    """
    pass


@router.get("/ai_analysis", status_code=status.HTTP_200_OK)
async def ai_analysis(
    id_vacancy: UUID,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> str | dict[str, Any] | None:
    return await analyze_vacancy_from_db(vacancy_id=id_vacancy, user_id=current_user.id, session=db)
