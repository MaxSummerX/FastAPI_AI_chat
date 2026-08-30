import asyncio
from typing import Any
from uuid import UUID

from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.application.exceptions.analysis import InvalidAnalysisTypeError
from app.application.exceptions.llm import LLMGenerationError
from app.application.exceptions.vacancy import VacancyNotFoundError
from app.application.prompts.analysis import (
    MATCHING_PROMPT,
    PREPARATION_PROMPT,
    PRIORITIZATION_PROMPT,
    SKILL_GAP_PROMPT,
)
from app.domain.enums.analysis import AnalysisType
from app.domain.repositories.vacancies import IVacancyRepository
from app.infrastructure.llms.openai import AsyncOpenAILLM


class VacancyAnalyzer:
    """
    AI-анализ вакансий через LLM.

    Типы анализа:
    - matching: соответствие кандидата вакансии
    - prioritization: оценка привлекательности
    - preparation: подготовка к интервью
    - skill_gap: анализ пробелов в навыках
    - custom: пользовательский промпт
    """

    def __init__(self, llm: AsyncOpenAILLM, vacancy_repo: IVacancyRepository):
        self.llm = llm
        self.vacancy_repo = vacancy_repo

    @staticmethod
    def _prompt_choice(analysis_type: AnalysisType) -> tuple[str, bool]:
        """
        Возвращает промпт для указанного типа анализа.

        Returns:
            Кортеж (промпт, нужен_ли_резюме)

        Raises:
            InvalidAnalysisTypeError: Если тип анализа не поддерживается
        """
        match analysis_type:
            case AnalysisType.MATCHING:
                return MATCHING_PROMPT, True
            case AnalysisType.SKILL_GAP:
                return SKILL_GAP_PROMPT, True
            case AnalysisType.PREPARATION:
                return PREPARATION_PROMPT, False
            case AnalysisType.PRIORITIZATION:
                return PRIORITIZATION_PROMPT, False
            case _:
                raise InvalidAnalysisTypeError(f"Неподдерживаемый тип анализа: {analysis_type}")

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((TimeoutError, ConnectionError)),
        reraise=True,
    )
    async def _call_llm(self, messages: list[dict[str, str]]) -> str | dict[str, Any]:
        """
        Вызывает LLM с автоматическим retry при транзиентных ошибках.

        Retry только на TimeoutError / ConnectionError с экспоненциальным backoff.
        LLMGenerationError (пустой ответ, бизнес-логика) — не ретраится, пробрасывается сразу.

        Raises:
            LLMGenerationError: Пустой ответ или исчерпаны все попытки
        """
        try:
            result = await self.llm.generate_response(messages)

            if not result:
                raise LLMGenerationError("LLM вернул пустой ответ")

            return result

        except LLMGenerationError:
            raise

        except (TimeoutError, ConnectionError):
            logger.warning("Транзиентная ошибка LLM, tenacity выполнит retry...")
            raise  # tenacity перехватит и решит: retry или стоп

        except Exception as e:
            logger.error(f"Неожиданная ошибка при вызове LLM: {e}")
            raise LLMGenerationError("Не удалось получить ответ от LLM") from e

    async def analyze(
        self,
        content: dict,
        analysis_type: AnalysisType,
        resume: str | None = None,
        custom_prompt: str | None = None,
    ) -> str:
        """
        Анализирует переданный контент вакансии.

        Raises:
            InvalidAnalysisTypeError: Если тип анализа не поддерживается
            LLMGenerationError: Если не удалось получить ответ от LLM
        """
        try:
            prompt, need_resume = self._prompt_choice(analysis_type)
        except InvalidAnalysisTypeError:
            # Для типа CUSTOM используем custom_prompt
            if analysis_type == AnalysisType.CUSTOM:
                if not custom_prompt:
                    raise InvalidAnalysisTypeError("Для типа CUSTOM обязателен custom_prompt") from None
                prompt, need_resume = custom_prompt, False
            else:
                raise

        # Добавляем резюме если нужно
        if need_resume and resume:
            content["user_resume"] = resume

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": str(content)},
        ]

        try:
            llm_result = await self._call_llm(messages)
            # LLM может вернуть dict для structured output
            return llm_result if isinstance(llm_result, str) else str(llm_result)

        except LLMGenerationError:
            raise
        except Exception as e:
            logger.error(f"Неожиданная ошибка при анализе: {e}")
            raise LLMGenerationError("Неожиданная ошибка при анализе") from e

    async def analyze_from_db(
        self,
        vacancy_id: UUID,
        analysis_type: AnalysisType,
        user_id: UUID,
        resume: str | None = None,
        custom_prompt: str | None = None,
    ) -> tuple[str, str]:
        """
        Анализирует вакансию из базы данных.

        Returns:
            Кортеж (результат_анализа, описание_типа_анализа)

        Raises:
            VacancyNotFoundError: Если вакансия не найдена
        """
        # Получаем вакансию (проверяем что она связана с пользователем)
        vacancy = await self.vacancy_repo.get_active_user_vacancy(user_id, vacancy_id)

        if vacancy is None:
            raise VacancyNotFoundError(f"Вакансия {vacancy_id} не найдена")

        if not vacancy.description:
            raise VacancyNotFoundError(f"У вакансии {vacancy_id} отсутствует описание")

        result = await self.analyze(
            content={"description": vacancy.description},
            analysis_type=analysis_type,
            resume=resume,
            custom_prompt=custom_prompt,
        )
        logger.info(f"Анализ {analysis_type.value} вакансии {str(vacancy_id)} успешно завершён")
        return result, analysis_type.description

    async def gather_responses(self, messages: list[str], connect: int) -> list[str | dict[str, Any] | None]:
        """
        Выполняет несколько запросов к LLM параллельно с ограничением.

        Args:
            messages: Список сообщений для анализа
            connect: Максимальное количество параллельных запросов

        Returns:
            Список результатов от LLM (None для неудачных запросов)
        """
        semaphore = asyncio.Semaphore(connect)

        async def request_with_semaphore(index: int, message: str) -> str | dict[str, Any] | None:
            async with semaphore:
                await asyncio.sleep(index * 0.1)
                try:
                    request = [
                        {"role": "system", "content": str(PREPARATION_PROMPT)},
                        {"role": "user", "content": str(message)},
                    ]
                    response: str | dict[str, Any] = await self._call_llm(request)
                    return response
                except LLMGenerationError as e:
                    logger.error(f"Ошибка при выполнении запроса {index}: {e}")
                    return None
                except Exception as e:
                    logger.error(f"Неожиданная ошибка при запросе {index}: {e}")
                    return None

        tasks = [request_with_semaphore(i, message) for i, message in enumerate(messages)]
        return list(await asyncio.gather(*tasks))
