from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.depends.db_depends import get_async_postgres_db
from app.models.users import User as UserModel
from app.models.vacancies import Vacancy as VacancyModel


router = APIRouter(prefix="/statistics", tags=["Statistics"])


@router.get("/active_vacancies")
async def active_vacancies(db: AsyncSession = Depends(get_async_postgres_db)) -> dict[str, int]:
    result_from_db = await db.scalars(select(func.count(VacancyModel.hh_id)).where(VacancyModel.is_archived.is_(False)))
    vacancies = result_from_db.one_or_none()
    if vacancies:
        return {"active_vacancies": int(vacancies)}
    else:
        return {"active_vacancies": 0}


@router.get("/active_users")
async def active_users(db: AsyncSession = Depends(get_async_postgres_db)) -> dict[str, int]:
    result_from_db = await db.scalars(select(func.count(UserModel.id)).where(UserModel.is_active.is_(True)))
    users = result_from_db.one_or_none()
    if users:
        return {"active_users": int(users)}
    else:
        return {"active_users": 0}
