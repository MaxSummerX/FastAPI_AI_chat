from typing import cast
from uuid import UUID

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.user_vacancies import UserVacancies
from app.domain.models.vacancy import Vacancy
from app.domain.repositories.vacancies import IVacancyRepository


class VacancySQLAlchemyRepository(IVacancyRepository):
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

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

    async def get_existing_hh_ids(self, hh_ids: list[str]) -> set[str]:
        result = await self.db.execute(select(Vacancy.hh_id).where(Vacancy.hh_id.in_(hh_ids)))
        return set(result.scalars().all())

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

    async def get_active_hh_ids(self) -> set[str]:
        result = await self.db.scalars(select(Vacancy.hh_id).where(Vacancy.is_archived.is_(False)))
        return set(result.all())

    async def bulk_save_with_links(
        self,
        vacancies: list[Vacancy],
        links: list[UserVacancies],
    ) -> None:
        self.db.add_all(vacancies)
        await self.db.flush()
        self.db.add_all(links)
        await self.db.commit()

    async def archive_by_hh_ids(self, hh_ids: list[str]) -> int:
        result = await self.db.execute(update(Vacancy).where(Vacancy.hh_id.in_(hh_ids)).values(is_archived=True))
        await self.db.commit()
        return int(cast(CursorResult, result).rowcount)
