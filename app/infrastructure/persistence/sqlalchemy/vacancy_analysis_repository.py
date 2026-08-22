from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums.analysis import AnalysisType
from app.domain.models.vacancy_analysis import VacancyAnalysis
from app.domain.repositories.vacancy_analyses import IVacancyAnalysisRepository


class VacancyAnalysisSQLAlchemyRepository(IVacancyAnalysisRepository):
    """SQLAlchemy-реализация репозитория анализов вакансий."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_all_for_user_vacancy(self, user_id: UUID, vacancy_id: UUID) -> list[VacancyAnalysis]:
        result = await self.db.scalars(
            select(VacancyAnalysis).where(
                VacancyAnalysis.vacancy_id == vacancy_id,
                VacancyAnalysis.user_id == user_id,
            )
        )
        return list(result.all())

    async def exists_for(
        self,
        user_id: UUID,
        vacancy_id: UUID,
        analysis_type: AnalysisType,
    ) -> bool:
        result = await self.db.scalar(
            select(VacancyAnalysis.id).where(
                VacancyAnalysis.vacancy_id == vacancy_id,
                VacancyAnalysis.analysis_type == analysis_type,
                VacancyAnalysis.user_id == user_id,
            )
        )
        return result is not None

    async def save(self, analysis: VacancyAnalysis) -> VacancyAnalysis:
        self.db.add(analysis)
        await self.db.commit()
        await self.db.refresh(analysis)
        return analysis

    async def get_by_id_for_user(self, user_id: UUID, analysis_id: UUID) -> VacancyAnalysis | None:
        result = await self.db.scalars(
            select(VacancyAnalysis).where(
                VacancyAnalysis.id == analysis_id,
                VacancyAnalysis.user_id == user_id,
            )
        )
        analysis: VacancyAnalysis | None = result.first()
        return analysis

    async def delete(self, analysis: VacancyAnalysis) -> None:
        await self.db.delete(analysis)
        await self.db.commit()
