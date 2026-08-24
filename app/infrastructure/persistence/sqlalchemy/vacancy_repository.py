from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import CursorResult, asc, case, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.vacancy import VacancyPaginationResponse, VacancyResponse
from app.domain.enums.experience import Experience, OrderField
from app.domain.models.user_vacancies import UserVacancies
from app.domain.models.vacancy import Vacancy
from app.domain.repositories.vacancies import IVacancyRepository
from app.infrastructure.persistence.sqlalchemy.db_optimizer import optimized_query


class VacancySQLAlchemyRepository(IVacancyRepository):
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def rollback(self) -> None:
        """Откат текущей транзакции (восстановление после ошибок flush)."""
        await self.db.rollback()

    async def get_active_user_vacancy(self, user_id: UUID, vacancy_id: UUID) -> Vacancy | None:
        result: Vacancy | None = await self.db.scalar(
            select(Vacancy)
            .join(UserVacancies)
            .where(
                UserVacancies.user_id == user_id,
                Vacancy.id == vacancy_id,
                UserVacancies.is_active.is_(True),
            )
        )
        return result

    async def get_existing_hh_id_map(self, hh_ids: list[str]) -> dict[str, UUID]:
        result = await self.db.execute(select(Vacancy.hh_id, Vacancy.id).where(Vacancy.hh_id.in_(hh_ids)))
        return {row[0]: row[1] for row in result.all()}

    async def get_user_linked_hh_ids(self, user_id: UUID, hh_ids: list[str]) -> set[str]:
        result = await self.db.execute(
            select(Vacancy.hh_id)
            .join(UserVacancies)
            .where(
                UserVacancies.user_id == user_id,
                Vacancy.hh_id.in_(hh_ids),
            )
        )
        return set(result.scalars().all())

    async def get_active_hh_ids(self, published_older: timedelta | None = None) -> set[str]:
        stmt = select(Vacancy.hh_id).where(Vacancy.is_archived.is_(False))
        if published_older is not None:
            stmt = stmt.where(Vacancy.published_at < func.now() - published_older)
        result = await self.db.scalars(stmt)
        return set(result.all())

    async def bulk_save_with_links(
        self,
        vacancies: list[Vacancy],
        links: list[UserVacancies],
        user_id: UUID,
    ) -> None:
        self.db.add_all(vacancies)
        await self.db.flush()

        # Связи для новых вакансий — после flush у них есть ID
        for vacancy in vacancies:
            self.db.add(UserVacancies(user_id=user_id, vacancy_id=vacancy.id))

        self.db.add_all(links)
        await self.db.commit()

    async def update_archive_statuses(self, hh_ids: dict[str, bool]) -> int:
        result = await self.db.execute(
            update(Vacancy)
            .where(Vacancy.hh_id.in_(hh_ids.keys()))
            .values(
                is_archived=case(
                    *[(Vacancy.hh_id == hh_id, value) for hh_id, value in hh_ids.items()],
                    else_=Vacancy.is_archived,
                )
            )
        )
        await self.db.commit()
        return int(cast(CursorResult, result).rowcount)

    async def get_by_hh_id(self, hh_id: str) -> Vacancy | None:
        result = await self.db.scalars(optimized_query(Vacancy, VacancyResponse).where(Vacancy.hh_id == hh_id))
        vacancy: Vacancy | None = result.one_or_none()
        return vacancy

    async def get_user_vacancy_with_favorite(self, user_id: UUID, vacancy_id: UUID) -> tuple[Vacancy, bool] | None:
        result = await self.db.execute(
            optimized_query(Vacancy, VacancyResponse)
            .join(UserVacancies)
            .where(
                UserVacancies.user_id == user_id,
                Vacancy.id == vacancy_id,
                UserVacancies.is_active.is_(True),
            )
            .add_columns(UserVacancies.is_favorite.label("is_favorite"))
        )
        row = result.one_or_none()
        return (row[0], row[1]) if row else None

    async def paginate_user_vacancies(
        self,
        user_id: UUID,
        *,
        tier: list[Experience] | None = None,
        favorite: bool | None = None,
        order_by: OrderField | None = None,
        order_desc: bool = False,
        cursor: tuple[datetime, UUID] | None = None,
        limit: int,
    ) -> list[tuple[Vacancy, bool]]:
        query = optimized_query(Vacancy, VacancyPaginationResponse).where(Vacancy.is_archived.is_(False))

        query = query.join(UserVacancies).where(
            UserVacancies.user_id == user_id,
            UserVacancies.is_active.is_(True),
        )

        if tier:
            query = query.where(Vacancy.experience_id.in_(tier))

        if favorite is not None:
            query = query.where(UserVacancies.is_favorite == favorite)

        if order_by:
            direction = desc if order_desc else asc
            query = query.order_by(direction(getattr(Vacancy, order_by.value)))

        if cursor:
            timestamp, cursor_id = cursor
            query = query.where(
                (Vacancy.created_at < timestamp) | ((Vacancy.created_at == timestamp) & (Vacancy.id < cursor_id))
            )

        # Составная сортировка для стабильности результатов
        query = query.order_by(Vacancy.created_at.desc(), Vacancy.id.desc())

        # +1 элемент для определения has_next
        result = await self.db.execute(
            query.add_columns(UserVacancies.is_favorite.label("is_favorite")).limit(limit + 1)
        )
        return [(row[0], row[1]) for row in result.all()]

    async def has_user_link(self, user_id: UUID, vacancy_id: UUID) -> bool:
        result = await self.db.scalar(
            select(UserVacancies.id).where(
                UserVacancies.user_id == user_id,
                UserVacancies.vacancy_id == vacancy_id,
            )
        )
        return result is not None

    async def save_with_link(self, vacancy: Vacancy, user_id: UUID) -> None:
        self.db.add(vacancy)
        await self.db.flush()
        self.db.add(UserVacancies(user_id=user_id, vacancy_id=vacancy.id, is_active=True))
        await self.db.commit()

    async def create_link(self, user_id: UUID, vacancy_id: UUID) -> None:
        self.db.add(UserVacancies(user_id=user_id, vacancy_id=vacancy_id, is_active=True))
        await self.db.commit()

    async def deactivate_user_link(self, user_id: UUID, vacancy_id: UUID) -> bool:
        result = await self.db.execute(
            update(UserVacancies)
            .where(UserVacancies.user_id == user_id, UserVacancies.vacancy_id == vacancy_id)
            .values(is_active=False)
            .returning(UserVacancies.id)
        )
        link_id = result.scalar_one_or_none()
        if link_id is None:
            return False
        await self.db.commit()
        return True

    async def set_favorite(self, user_id: UUID, vacancy_id: UUID, is_favorite: bool) -> bool:
        result = await self.db.execute(
            update(UserVacancies)
            .where(UserVacancies.user_id == user_id, UserVacancies.vacancy_id == vacancy_id)
            .values(is_favorite=is_favorite)
            .returning(UserVacancies.id)
        )
        link_id = result.scalar_one_or_none()
        if link_id is None:
            return False
        await self.db.commit()
        return True
