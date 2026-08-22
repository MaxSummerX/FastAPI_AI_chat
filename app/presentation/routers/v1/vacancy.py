from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger

from app.application.exceptions.vacancy import InvalidVacancyCursorError
from app.application.schemas.pagination import PaginatedResponse
from app.application.schemas.vacancy import VacancyPaginationResponse, VacancyResponse
from app.application.services.vacancy_service import VacancyService
from app.domain.enums.experience import Experience, OrderField
from app.domain.models.user import User as UserModel
from app.infrastructure.persistence.pagination import (
    DEFAULT_PER_PAGE,
    MINIMUM_PER_PAGE,
)
from app.presentation.dependencies import get_current_user, get_vacancy_service
from app.presentation.routers.v1 import vacancy_analysis


router = APIRouter(prefix="/vacancies")

TAGS = "Vacancies_v1"


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    tags=[TAGS],
    summary="Получить вакансии пользователя с пагинацией",
)
async def get_all_vacancies(
    tier: list[Experience] | None = Query(
        None,
        description="Фильтрация по уровню опыта. Можно выбрать несколько значений. Если не указано - возвращаются все вакансии.",
    ),
    favorite: bool | None = Query(
        None,
        description="Фильтрация по избранному: true — только избранные, false — все кроме избранных, не указано — все вакансии",
    ),
    limit: int = Query(
        default=DEFAULT_PER_PAGE, ge=MINIMUM_PER_PAGE, description="Размер страницы (1-100). По умолчанию: 20"
    ),
    cursor: str | None = Query(
        default=None, description="Курсор для следующей страницы. Берётся из предыдущего ответа"
    ),
    order_by: OrderField | None = Query(default=None, description="Поле для сортировки"),
    order_desc: bool = Query(default=False, description="Сортировка по убыванию"),
    current_user: UserModel = Depends(get_current_user),
    vacancy_service: VacancyService = Depends(get_vacancy_service),
) -> PaginatedResponse[VacancyPaginationResponse]:
    """
    Получить вакансии пользователя с пагинацией (курсорной).
    """
    logger.info(
        f"Запрос на получение вакансий пользователя {current_user.id} "
        f"с пагинацией: limit={limit}, cursor={'да' if cursor else 'нет'}"
    )

    try:
        page = await vacancy_service.get_paginated(
            current_user.id,
            tier=tier,
            favorite=favorite,
            order_by=order_by,
            order_desc=order_desc,
            cursor=cursor,
            limit=limit,
        )
    except InvalidVacancyCursorError as e:
        logger.warning(f"Невалидный курсор от пользователя {current_user.id}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None

    logger.info(f"Возвращено {len(page.items)} вакансий, has_next={page.has_next}")

    items = []
    for vacancy, is_fav in page.items:
        item = VacancyPaginationResponse.model_validate(vacancy).model_dump()
        item["is_favorite"] = is_fav
        items.append(VacancyPaginationResponse(**item))

    return PaginatedResponse(
        items=items,
        next_cursor=page.next_cursor,
        has_next=page.has_next,
    )


@router.post(
    "/head_hunter/{hh_id_vacancy}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=[TAGS],
    summary="Добавить вакансию по hh_id в пул пользователя",
)
async def hh_vacancy(
    hh_id_vacancy: str,
    current_user: UserModel = Depends(get_current_user),
    vacancy_service: VacancyService = Depends(get_vacancy_service),
) -> None:
    """
    Добавляет вакансию по hh_id в пул пользователя.
    Если вакансия уже есть в БД - просто создаёт связь.
    Если нет - импортирует из hh.ru и создаёт связь.
    """
    logger.info(f"Запрос на получение вакансии по HH.ru id {hh_id_vacancy} для пользователя {current_user.id}")

    try:
        await vacancy_service.add_hh_vacancy(current_user.id, hh_id_vacancy)
    except Exception as e:
        logger.error(f"Ошибка при импорте вакансии {hh_id_vacancy}: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vacancy not found") from None

    logger.info(f"Вакансия {hh_id_vacancy} добавлена пользователю {current_user.email}")
    return


@router.get(
    "/{id_vacancy}",
    status_code=status.HTTP_200_OK,
    tags=[TAGS],
    summary="Получить вакансию по UUID",
)
async def get_vacancy(
    id_vacancy: UUID,
    current_user: UserModel = Depends(get_current_user),
    vacancy_service: VacancyService = Depends(get_vacancy_service),
) -> VacancyResponse:
    """
    Получает вакансию по UUID (только активная связь с пользователем).
    """
    logger.info(f"Запрос на получение вакансии {id_vacancy} пользователя {current_user.id}")

    row = await vacancy_service.get_user_vacancy(current_user.id, id_vacancy)

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vacancy not found")

    vacancy, is_favorite = row
    response = VacancyResponse.model_validate(vacancy).model_dump()
    response["is_favorite"] = is_favorite
    return VacancyResponse(**response)


@router.delete(
    "/{id_vacancy}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=[TAGS],
    summary="Мягкое удаление вакансии",
)
async def delete_vacancy(
    id_vacancy: UUID,
    current_user: UserModel = Depends(get_current_user),
    vacancy_service: VacancyService = Depends(get_vacancy_service),
) -> None:
    """
    Мягкое удаление вакансии
    """
    logger.info(f"Запрос на удаление вакансии {id_vacancy} пользователя {current_user.id}")

    if not await vacancy_service.deactivate(current_user.id, id_vacancy):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vacancy not found")

    logger.info(f"Вакансия {id_vacancy} удалёна")


@router.put(
    "/{id_vacancy}/favorite",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=[TAGS],
    summary="Добавить вакансию в избранное",
)
async def add_to_favorites(
    id_vacancy: UUID,
    current_user: UserModel = Depends(get_current_user),
    vacancy_service: VacancyService = Depends(get_vacancy_service),
) -> None:
    """
    Добавить вакансию в избранное
    """
    logger.info(f"Запрос на добавление вакансии {id_vacancy} в избранное")

    if not await vacancy_service.set_favorite(current_user.id, id_vacancy, True):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vacancy not found")

    logger.info(f"Вакансия {id_vacancy} добавлена в избранное")
    return


@router.delete(
    "/{id_vacancy}/favorite",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=[TAGS],
    summary="Удалить вакансию из избранного",
)
async def remove_from_favorites(
    id_vacancy: UUID,
    current_user: UserModel = Depends(get_current_user),
    vacancy_service: VacancyService = Depends(get_vacancy_service),
) -> None:
    """
    Удалить вакансию из избранного
    """
    logger.info(f"Запрос на удаление вакансии {id_vacancy} из избранного")

    if not await vacancy_service.set_favorite(current_user.id, id_vacancy, False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vacancy not found")

    logger.info(f"Вакансия {id_vacancy} удалена из избранного")
    return


router.include_router(vacancy_analysis.router)
