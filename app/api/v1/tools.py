from typing import Any

from fastapi import APIRouter, Depends, status
from loguru import logger

from app.auth.dependencies import get_current_user
from app.models.users import User as UserModel
from app.tools.headhunter.find_vacancies import fetch_all_hh_vacancies, fetch_full_vacancy
from app.tools.invite.invite_tools import generate_invite_codes, list_unused_codes


router_V1 = APIRouter(prefix="/tools", tags=["Tools"])


@router_V1.get("/vacancies/{id_vacancies}", status_code=status.HTTP_200_OK)
async def vacancies(id_vacancies: str, current_user: UserModel = Depends(get_current_user)) -> dict[str, Any]:
    """
    Получается информацию о вакансии по id
    """
    logger.info(f"Получен запрос на выгрузку информации о вакансии id: {id_vacancies}")
    result = await fetch_full_vacancy(id_vacancies)

    return result


@router_V1.get("/vacancies", status_code=status.HTTP_200_OK)
async def fetch_vacancies(query: str, current_user: UserModel = Depends(get_current_user)) -> dict:
    """
    Выгружает вакансии по поисковому запросу в json файл.
    запрос -> django OR fastapi OR aiohttp OR litestar OR flask
    """
    logger.info(f"Получен запрос с параметром st: '{query}'")
    result = await fetch_all_hh_vacancies(query)
    return result


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
