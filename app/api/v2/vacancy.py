from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from httpx import AsyncClient
from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v2 import vacancy_analysis
from app.auth.dependencies import get_current_user
from app.depends.db_depends import get_async_postgres_db
from app.enum.experience import Experience
from app.models import Vacancy as VacancyModel
from app.models.user_vacancies import UserVacancies as UserVacanciesModel
from app.models.users import User as UserModel
from app.schemas.pagination import PaginatedResponse
from app.schemas.vacancies import VacancyPaginationResponse, VacancyResponse
from app.tools.headhunter.find_vacancies import vacancy_create
from app.tools.headhunter.headhunter_client import get_hh_client
from app.utils.db_optimizer import optimized_query
from app.utils.utils_for_pagination import (
    calculate_has_more,
    decode_cursor,
    encode_cursor,
    trim_excess_item,
    validate_pagination_limit,
)


router = APIRouter(prefix="/vacancies")

TAGS = "Vacancies_v2"
DEFAULT_PER_PAGE = 20
MINIMUM_PER_PAGE = 1
MAXIMUM_PER_PAGE = 100


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
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> PaginatedResponse[VacancyPaginationResponse]:
    """
    Получить вакансий пользователя с пагинацией (курсорной).
    """
    logger.info(
        f"Запрос на получение вакансий пользователя {current_user.id} "
        f"с пагинацией: limit={limit}, cursor={'да' if cursor else 'нет'}"
    )
    # Валидируем limit
    limit = validate_pagination_limit(limit, default=DEFAULT_PER_PAGE, maximum=MAXIMUM_PER_PAGE)

    # Формируем базовый запрос
    base_query = optimized_query(VacancyModel, VacancyPaginationResponse)

    query = base_query.join(UserVacanciesModel).where(
        UserVacanciesModel.user_id == current_user.id,
        VacancyModel.is_active.is_(True),
    )

    if tier:
        query = query.where(VacancyModel.experience_id.in_(tier))

    if favorite is not None:
        query = query.where(UserVacanciesModel.is_favorite == favorite)

    # Применяем курсор если указан
    if cursor:
        try:
            # Используем составной ключ (timestamp, id_uuid) для точного позиционирования
            timestamp, cursor_id_str = decode_cursor(cursor)
            id_uuid = UUID(cursor_id_str)

            query = query.where(
                (VacancyModel.created_at < timestamp)
                | ((VacancyModel.created_at == timestamp) & (VacancyModel.id < id_uuid))
            )
            logger.debug(f"Применён курсор: timestamp={timestamp}, id={id_uuid}")
        except ValueError as e:
            logger.warning(f"Невалидный курсор от пользователя {current_user.id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid cursor format: {str(e)}"
            ) from None

    # Используем составную сортировку для стабильности результатов
    query = query.order_by(VacancyModel.created_at.desc(), VacancyModel.id.desc())

    # Берём на один элемент больше для проверки has_next
    result = await db.execute(query.add_columns(UserVacanciesModel.is_favorite.label("is_favorite")).limit(limit + 1))
    rows = list(result.all())  # ← кортежи (Vacancy, is_favorite)

    # Эти функции работают с кортежами без изменений!
    has_next = calculate_has_more(rows, limit)
    rows = trim_excess_item(rows, limit, reverse=False)

    # Формируем курсор — нужно распаковать кортеж
    next_cursor = None
    if rows and has_next:
        last_vacancy, _ = rows[-1]  # ← распаковываем: Vacancy, is_favorite
        next_cursor = encode_cursor(last_vacancy.created_at, last_vacancy.id)

    logger.info(f"Возвращено {len(rows)} вакансий, has_next={has_next}")

    # Формируем ответ с is_favorite
    items = []
    for vacancy, is_fav in rows:  # ← распаковываем кортеж
        item = VacancyPaginationResponse.model_validate(vacancy).model_dump()
        item["is_favorite"] = is_fav
        items.append(VacancyPaginationResponse(**item))

    return PaginatedResponse(
        items=items,
        next_cursor=next_cursor,
        has_next=has_next,
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
    db: AsyncSession = Depends(get_async_postgres_db),
    hh_client: AsyncClient = Depends(get_hh_client),
) -> None:
    """
    Добавляет вакансию по hh_id в пул пользователя.
    Если вакансия уже есть в БД - просто создаёт связь.
    Если нет - импортирует из hh.ru и создаёт связь.
    """
    logger.info(f"Запрос на получение вакансии по HH.ru id {hh_id_vacancy} для пользователя {current_user.id}")
    # Проверяем наличие вакансии в БД (без фильтра по пользователю)
    base_query = optimized_query(VacancyModel, VacancyResponse)
    result = await db.scalars(
        base_query.where(
            VacancyModel.hh_id == hh_id_vacancy,
            VacancyModel.is_active.is_(True),
        )
    )

    vacancy = result.one_or_none()

    # Если вакансии нет в БД - импортируем из hh.ru
    if not vacancy:
        logger.info(f"Вакансия {hh_id_vacancy} не найдена в БД, создание")
        try:
            vacancy_obj = await vacancy_create(hh_id=hh_id_vacancy, query="Personal request", hh_client=hh_client)

            db.add(vacancy_obj)
            await db.flush()

            link = UserVacanciesModel(user_id=current_user.id, vacancy_id=vacancy_obj.id)
            db.add(link)
            await db.commit()

            logger.info(f"Вакансия {hh_id_vacancy} успешно импортирована")

        except Exception as e:
            logger.error(f"Ошибка при импорте вакансии {hh_id_vacancy}: {e}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vacancy not found") from None
    else:
        # Вакансия есть в БД - проверяем есть ли связь с пользователем
        link_check = await db.execute(
            select(UserVacanciesModel).where(
                UserVacanciesModel.user_id == current_user.id,
                UserVacanciesModel.vacancy_id == vacancy.id,
            )
        )
        if not link_check.one_or_none():
            # Связи нет - создаём
            link = UserVacanciesModel(user_id=current_user.id, vacancy_id=vacancy.id)
            db.add(link)
            await db.commit()

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
    db: AsyncSession = Depends(get_async_postgres_db),
) -> VacancyResponse:
    """
    Получает вакансию по UUID. Оптимизированный запрос только для полей из VacancyResponse.
    """
    logger.info(f"Запрос на получение вакансии {id_vacancy} пользователя {current_user.id}")

    # optimized_query автоматически применяет load_only для полей из VacancyResponse
    base_query = optimized_query(VacancyModel, VacancyResponse)
    result = await db.execute(
        base_query.join(UserVacanciesModel)
        .where(
            UserVacanciesModel.user_id == current_user.id,
            VacancyModel.id == id_vacancy,
            VacancyModel.is_active.is_(True),
        )
        .add_columns(UserVacanciesModel.is_favorite.label("is_favorite"))
    )

    row = result.one_or_none()

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vacancy not found")

    vacancy, is_favorite = row  # распаковываем кортеж (Vacancy, is_favorite)
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
    db: AsyncSession = Depends(get_async_postgres_db),
) -> None:
    """
    Мягкое удаление вакансии
    """
    logger.info(f"Запрос на удаление вакансии {id_vacancy} пользователя {current_user.id}")

    # Проверяем что пользователь связан с вакансией
    link_check = await db.execute(
        select(UserVacanciesModel).where(
            UserVacanciesModel.user_id == current_user.id,
            UserVacanciesModel.vacancy_id == id_vacancy,
        )
    )
    if not link_check.one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vacancy not found")

    result = await db.execute(
        update(VacancyModel)
        .where(VacancyModel.id == id_vacancy, VacancyModel.is_active.is_(True))
        .values(is_active=False)
        .returning(VacancyModel.id)
    )

    deleted_vacancy = result.scalar_one_or_none()

    if not deleted_vacancy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vacancy not found")

    await db.commit()

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
    db: AsyncSession = Depends(get_async_postgres_db),
) -> None:
    """
    Добавить вакансию в избранное
    """
    logger.info(f"Запрос на добавление вакансии {id_vacancy} в избранное")

    result = await db.execute(
        update(UserVacanciesModel)
        .where(UserVacanciesModel.user_id == current_user.id, UserVacanciesModel.vacancy_id == id_vacancy)
        .values(is_favorite=True)
        .returning(UserVacanciesModel.id)
    )

    link_id = result.scalar_one_or_none()

    if not link_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vacancy not found")

    await db.commit()

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
    db: AsyncSession = Depends(get_async_postgres_db),
) -> None:
    """
    Удалить вакансию из избранного
    """
    logger.info(f"Запрос на удаление вакансии {id_vacancy} из избранного")

    result = await db.execute(
        update(UserVacanciesModel)
        .where(UserVacanciesModel.user_id == current_user.id, UserVacanciesModel.vacancy_id == id_vacancy)
        .values(is_favorite=False)
        .returning(UserVacanciesModel.id)
    )

    link_id = result.scalar_one_or_none()

    if not link_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vacancy not found")

    await db.commit()

    logger.info(f"Вакансия {id_vacancy} удалена из избранного")
    return


router.include_router(vacancy_analysis.router)
