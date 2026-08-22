"""
Сервис вакансий.

Use cases: пагинация с курсором, добавление вакансии по hh_id,
получение/удаление вакансии, управление избранным.
"""

from dataclasses import dataclass
from uuid import UUID

from loguru import logger

from app.application.exceptions.vacancy import InvalidVacancyCursorError
from app.application.services.vacancy_import_service import create_vacancy_object
from app.domain.enums.experience import Experience, OrderField
from app.domain.models.vacancy import Vacancy
from app.domain.repositories.vacancies import IVacancyRepository
from app.infrastructure.hh.headhunter_client import get_hh_client
from app.infrastructure.persistence.pagination import (
    DEFAULT_PER_PAGE,
    MAXIMUM_PER_PAGE,
    calculate_has_more,
    decode_cursor,
    encode_cursor,
    trim_excess_item,
    validate_pagination_limit,
)


@dataclass
class VacancyPage:
    """Страница вакансий с курсорной пагинацией."""

    items: list[tuple[Vacancy, bool]]
    next_cursor: str | None
    has_next: bool


class VacancyService:
    """
    Сервис управления вакансиями пользователя.

    Объединяет чтение с фильтрами и курсорной пагинацией,
    добавление вакансий с hh.ru (импорт или связывание),
    мягкое удаление и управление избранным.
    """

    def __init__(self, vacancy_repo: IVacancyRepository) -> None:
        self.vacancy_repo = vacancy_repo

    async def get_paginated(
        self,
        user_id: UUID,
        *,
        tier: list[Experience] | None = None,
        favorite: bool | None = None,
        order_by: OrderField | None = None,
        order_desc: bool = False,
        cursor: str | None = None,
        limit: int,
    ) -> VacancyPage:
        """
        Страница активных вакансий пользователя с флагом избранного.

        Raises:
            InvalidVacancyCursorError: При невалидном формате курсора
        """
        limit = validate_pagination_limit(limit, default=DEFAULT_PER_PAGE, maximum=MAXIMUM_PER_PAGE)

        decoded_cursor = None
        if cursor:
            try:
                timestamp, cursor_id_str = decode_cursor(cursor)
                decoded_cursor = (timestamp, UUID(cursor_id_str))
            except ValueError as e:
                raise InvalidVacancyCursorError(f"Invalid cursor format: {e}") from e

        rows = await self.vacancy_repo.paginate_user_vacancies(
            user_id,
            tier=tier,
            favorite=favorite,
            order_by=order_by,
            order_desc=order_desc,
            cursor=decoded_cursor,
            limit=limit,
        )

        # rows на один элемент больше — для проверки has_next
        has_next = calculate_has_more(rows, limit)
        rows = trim_excess_item(rows, limit, reverse=False)

        next_cursor = None
        if rows and has_next:
            last_vacancy, _ = rows[-1]
            next_cursor = encode_cursor(last_vacancy.created_at, last_vacancy.id)

        return VacancyPage(items=rows, next_cursor=next_cursor, has_next=has_next)

    async def add_hh_vacancy(self, user_id: UUID, hh_id: str) -> None:
        """
        Добавить вакансию по hh_id в пул пользователя.

        Если вакансия уже есть в БД — создаёт связь (если её нет),
        иначе импортирует с hh.ru и создаёт связь.
        """
        vacancy = await self.vacancy_repo.get_by_hh_id(hh_id)

        if not vacancy:
            logger.info(f"Вакансия {hh_id} не найдена в БД, импорт с hh.ru")
            hh_client = await get_hh_client()
            vacancy_obj = await create_vacancy_object(hh_id=hh_id, query="Personal request", hh_client=hh_client)
            await self.vacancy_repo.save_with_link(vacancy_obj, user_id)
            logger.info(f"Вакансия {hh_id} успешно импортирована")
        else:
            if not await self.vacancy_repo.has_user_link(user_id, vacancy.id):
                await self.vacancy_repo.create_link(user_id, vacancy.id)

    async def get_user_vacancy(self, user_id: UUID, vacancy_id: UUID) -> tuple[Vacancy, bool] | None:
        """
        Получить активную вакансию пользователя с флагом избранного.
        """
        return await self.vacancy_repo.get_user_vacancy_with_favorite(user_id, vacancy_id)

    async def deactivate(self, user_id: UUID, vacancy_id: UUID) -> bool:
        """
        Мягкое удаление вакансии (деактивация связи).

        Returns:
            True если связь найдена и деактивирована
        """
        return await self.vacancy_repo.deactivate_user_link(user_id, vacancy_id)

    async def set_favorite(self, user_id: UUID, vacancy_id: UUID, is_favorite: bool) -> bool:
        """
        Установить/снять избранное.

        Returns:
            True если связь найдена и обновлена
        """
        return await self.vacancy_repo.set_favorite(user_id, vacancy_id, is_favorite)
