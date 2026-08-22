"""
Сервис анализов вакансий.

Use cases: список анализов вакансии, создание анализа через LLM,
список доступных типов.
"""

from uuid import UUID

from loguru import logger

from app.application.exceptions.analysis import InvalidAnalysisTypeError
from app.application.exceptions.vacancy import (
    AnalysisAlreadyExistsError,
    ResumeRequiredError,
    ResumeTooShortError,
    VacancyNotFoundError,
)
from app.application.services.vacancy_analyzer import VacancyAnalyzer
from app.domain.enums.analysis import AnalysisType
from app.domain.models.vacancy_analysis import VacancyAnalysis
from app.domain.repositories.vacancies import IVacancyRepository
from app.domain.repositories.vacancy_analyses import IVacancyAnalysisRepository


MIN_SIZE_RESUME = 300


class VacancyAnalysisService:
    """
    Сервис управления анализами вакансий пользователя.

    Создание анализа: валидация типа/резюме, проверка дубликата,
    генерация через LLM (VacancyAnalyzer), сохранение результата.
    """

    def __init__(
        self,
        analysis_repo: IVacancyAnalysisRepository,
        vacancy_repo: IVacancyRepository,
        analyzer: VacancyAnalyzer,
    ) -> None:
        self.analysis_repo = analysis_repo
        self.vacancy_repo = vacancy_repo
        self.analyzer = analyzer

    async def get_all_for_vacancy(self, user_id: UUID, vacancy_id: UUID) -> list[VacancyAnalysis]:
        """
        Все анализы вакансии пользователя.

        Raises:
            VacancyNotFoundError: Если вакансия не найдена или не связана с пользователем
        """
        vacancy = await self.vacancy_repo.get_active_user_vacancy(user_id, vacancy_id)
        if vacancy is None:
            raise VacancyNotFoundError(f"Вакансия {vacancy_id} не найдена")

        return await self.analysis_repo.get_all_for_user_vacancy(user_id, vacancy_id)

    async def create_analysis(
        self,
        user_id: UUID,
        vacancy_id: UUID,
        *,
        analysis_type: AnalysisType,
        custom_prompt: str | None,
        title: str | None,
        resume: str | None,
    ) -> VacancyAnalysis:
        """
        Создать анализ вакансии заданного типа.

        Args:
            user_id: ID пользователя
            vacancy_id: ID вакансии
            analysis_type: Тип анализа
            custom_prompt: Пользовательский промпт (обязателен для CUSTOM)
            title: Заголовок (обязателен для CUSTOM, иначе из enum)
            resume: Резюме пользователя

        Returns:
            Сохранённый объект VacancyAnalysis

        Raises:
            InvalidAnalysisTypeError: Некорректный тип анализа / нет custom_prompt
            AnalysisAlreadyExistsError: Анализ этого типа уже существует
            ResumeRequiredError: Резюме не загружено
            ResumeTooShortError: Резюме короче MIN_SIZE_RESUME символов
            VacancyNotFoundError: Вакансия не найдена
            LLMGenerationError: Ошибка LLM
        """
        if analysis_type == AnalysisType.CUSTOM:
            if not custom_prompt:
                raise InvalidAnalysisTypeError("custom_prompt is required for CUSTOM type")
            if not title:
                raise InvalidAnalysisTypeError("title is required for CUSTOM type")
            result_title = title
        else:
            # Системные анализы - title из enum
            result_title = analysis_type.display_name

        # Проверяем существующий анализ у этого пользователя
        if await self.analysis_repo.exists_for(user_id, vacancy_id, analysis_type):
            raise AnalysisAlreadyExistsError(f"Analysis {analysis_type.value} already exists")

        if resume is None:
            raise ResumeRequiredError("Resume not found. Please upload your resume first.")

        if len(resume) < MIN_SIZE_RESUME:
            raise ResumeTooShortError(f"Resume is too short. Minimum {MIN_SIZE_RESUME} characters required.")

        result, prompt_template = await self.analyzer.analyze_from_db(
            vacancy_id=vacancy_id,
            analysis_type=analysis_type,
            custom_prompt=custom_prompt,
            user_id=user_id,
            resume=resume,
        )

        analysis = VacancyAnalysis(
            vacancy_id=vacancy_id,
            user_id=user_id,
            title=result_title,
            analysis_type=analysis_type,
            prompt_template=prompt_template,
            custom_prompt=custom_prompt,
            result_text=result,
        )
        saved = await self.analysis_repo.save(analysis)
        logger.info(f"Анализ {analysis_type.value} вакансии {vacancy_id} сохранён: {saved.id}")
        return saved
