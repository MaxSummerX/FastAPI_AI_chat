"""
Репозитории анализов вакансий.

Интерфейсы для работы с результатами AI-анализа вакансий.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.enums.analysis import AnalysisType
from app.domain.models.vacancy_analysis import VacancyAnalysis


class IVacancyAnalysisRepository(ABC):
    """
    Интерфейс репозитория для работы с анализами вакансий.
    """

    @abstractmethod
    async def get_all_for_user_vacancy(self, user_id: UUID, vacancy_id: UUID) -> list[VacancyAnalysis]:
        """
        Получить все анализы вакансии пользователя.

        Args:
            user_id: ID пользователя
            vacancy_id: ID вакансии

        Returns:
            Список анализов (пустой, если нет)
        """
        pass

    @abstractmethod
    async def exists_for(
        self,
        user_id: UUID,
        vacancy_id: UUID,
        analysis_type: AnalysisType,
    ) -> bool:
        """
        Проверить существование анализа данного типа у вакансии пользователя.

        Args:
            user_id: ID пользователя
            vacancy_id: ID вакансии
            analysis_type: Тип анализа

        Returns:
            True если анализ уже существует
        """
        pass

    @abstractmethod
    async def save(self, analysis: VacancyAnalysis) -> VacancyAnalysis:
        """
        Сохранить новый анализ.

        Args:
            analysis: Объект VacancyAnalysis

        Returns:
            Сохранённый объект с присвоенным ID
        """
        pass

    @abstractmethod
    async def get_by_id_for_user(self, user_id: UUID, analysis_id: UUID) -> VacancyAnalysis | None:
        """
        Получить анализ по ID (только владелец).

        Returns:
            Анализ или None
        """
        pass

    @abstractmethod
    async def delete(self, analysis: VacancyAnalysis) -> None:
        """
        Удалить анализ (безвозвратно).

        Args:
            analysis: Объект VacancyAnalysis для удаления
        """
        pass
