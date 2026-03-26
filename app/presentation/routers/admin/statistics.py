from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.user_service import UserService
from app.domain.models.vacancy import Vacancy as VacancyModel
from app.presentation.dependencies import get_db, get_user_service


router = APIRouter(prefix="/statistics")


@router.get("/active_vacancies")
async def active_vacancies(db: AsyncSession = Depends(get_db)) -> dict[str, int]:
    """Возвращает количество активных (неархивных) вакансий в системе."""
    result_from_db = await db.scalars(select(func.count(VacancyModel.hh_id)).where(VacancyModel.is_archived.is_(False)))
    vacancies = result_from_db.one_or_none()
    if vacancies:
        return {"active_vacancies": int(vacancies)}
    else:
        return {"active_vacancies": 0}


@router.get("/active_users")
async def active_users(service: UserService = Depends(get_user_service)) -> dict[str, int]:
    """Возвращает количество активных пользователей в системе."""
    count_users = await service.active_users()
    if count_users:
        return {"active_users": count_users}
    else:
        return {"active_users": 0}
