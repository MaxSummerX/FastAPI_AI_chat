from typing import cast
from uuid import UUID

from sqlalchemy import CursorResult, case, select, update
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

    async def get_active_hh_ids(self) -> set[str]:
        result = await self.db.scalars(select(Vacancy.hh_id).where(Vacancy.is_archived.is_(False)))
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
