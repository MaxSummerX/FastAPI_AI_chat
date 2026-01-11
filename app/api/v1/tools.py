from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.depends.db_depends import get_async_postgres_db
from app.enum.experience import Experience
from app.models import Vacancy as VacancyModel
from app.models.users import User as UserModel
from app.schemas.vacancies import VacancyResponse
from app.tools.headhunter.find_vacancies import import_vacancies
from app.tools.invite.invite_tools import generate_invite_codes, list_unused_codes


router_V1 = APIRouter(prefix="/tools", tags=["Tools"])


@router_V1.get("/vacancies_hh/{hh_id_vacancy}", status_code=status.HTTP_200_OK)
async def hh_vacancy(
    hh_id_vacancy: str,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> dict[str, Any] | None:
    """
    Получается raw_data о вакансии по hh_id из базы данных сервиса
    """
    result = await db.scalars(
        select(VacancyModel.raw_data).where(
            VacancyModel.user_id == current_user.id, VacancyModel.hh_id == hh_id_vacancy
        )
    )
    logger.info(f"Пользователь {current_user.email} запросил raw_data о вакансии hh_id: {hh_id_vacancy}")
    raw_data: dict[str, Any] | None = result.one_or_none()
    return raw_data


@router_V1.get("/vacancies/{id_vacancy}", status_code=status.HTTP_200_OK)
async def get_vacancy(
    id_vacancy: UUID,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> VacancyResponse:
    logger.info(f"Запрос на получение вакансии {id_vacancy} пользователя {current_user.id}")
    result = await db.execute(
        select(VacancyModel).where(VacancyModel.user_id == current_user.id, VacancyModel.id == id_vacancy)
    )

    vacancy = cast(VacancyModel, result.scalar_one_or_none())

    if not vacancy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Вакансия не найдена")

    return cast(VacancyResponse, VacancyResponse.model_validate(vacancy))


@router_V1.get("/import_vacancies", status_code=status.HTTP_200_OK)
async def save_all_vacancies(
    query: str,
    background_tasks: BackgroundTasks,
    tiers: list[Experience] | None = Query(
        None,
        description="Фильтрация по уровню опыта. Можно выбрать несколько значений. Если не указано - возвращаются все вакансии.",
    ),
    db: AsyncSession = Depends(get_async_postgres_db),
    current_user: UserModel = Depends(get_current_user),
) -> dict[str, str]:
    """
    Выгружает с hh.ru вакансии по поисковому запросу в бд.
    запрос -> django OR fastapi OR aiohttp OR litestar OR flask OR sanic OR tornado

    Фильтрация сохранения вакансий по уровню опыта.

    Доступные значения tier:
    - noExperience: Без опыта
    - between1And3: От 1 до 3 лет
    - between3And6: От 3 до 6 лет
    - moreThan6: Более 6 лет
    """

    background_tasks.add_task(import_vacancies, query=query, tiers=tiers, user_id=current_user.id, session=db)

    return {"message": f"Импорт вакансий по запросу '{query}' запущен в фоновом режиме"}


@router_V1.get("/generate_code", status_code=status.HTTP_200_OK)
async def generate_invite(count: int, current_user: UserModel = Depends(get_current_user)) -> list[str]:
    """
    Генерирует указанное количество invite кодов
    """
    logger.info(f"Получен запрос на создание '{count}' invites")
    result = await generate_invite_codes(count)
    return result


@router_V1.get("/unused_code", status_code=status.HTTP_200_OK)
async def unused_code(current_user: UserModel = Depends(get_current_user)) -> list[str]:
    """
    Показывает все неиспользованные коды
    """
    logger.info("Получен запрос на получение доступных приглашений")
    result = await list_unused_codes()
    return result
