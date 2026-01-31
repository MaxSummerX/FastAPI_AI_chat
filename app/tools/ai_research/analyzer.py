from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enum.analysis import AnalysisType
from app.llms.openai import AsyncOpenAILLM
from app.models.user_vacancies import UserVacancies as UserVacanciesModel
from app.models.vacancies import Vacancy as VacancyModel
from app.tools.ai_research.exceptions import (
    InvalidAnalysisTypeError,
    LLMError,
    VacancyNotFoundError,
)
from app.tools.ai_research.llm import _call_llm_with_retry
from app.tools.ai_research.prompts import prompt_choice


async def analyze_vacancy(
    content: dict,
    llm: AsyncOpenAILLM,
    analysis_type: AnalysisType,
    resume: str | None = None,
    custom_prompt: str | None = None,
) -> str:
    """
    Returns:
        str результат_анализа

    Raises:

        UserNotFoundError: Если пользователь не найден
        InvalidAnalysisTypeError: Если тип анализа не поддерживается
        LLMError: Если не удалось получить ответ от LLM
    """
    try:
        prompt, need_resume = prompt_choice(analysis_type)
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

    # Формируем сообщения для LLM
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": str(content)},
    ]

    # Вызываем LLM с retry
    try:
        llm_result = await _call_llm_with_retry(llm, messages)
        # Преобразуем результат в строку (LLM может вернуть dict для structured output)
        result: str = llm_result if isinstance(llm_result, str) else str(llm_result)
        return result

    except LLMError:
        raise
    except Exception as e:
        logger.error(f"Неожиданная ошибка при анализе: {e}")
        raise LLMError(f"Неожиданная ошибка при анализе: {e}") from e


async def analyze_vacancy_from_db(
    llm: AsyncOpenAILLM,
    vacancy_id: UUID,
    analysis_type: AnalysisType,
    user_id: UUID,
    session: AsyncSession,
    resume: str | None = None,
    custom_prompt: str | None = None,
) -> tuple[str, str]:
    """
    Анализирует вакансию из базы данных с использованием LLM.

    Args:
        llm: Инстанс LLM (получается через dependency injection)
        vacancy_id: ID вакансии
        analysis_type: Тип анализа
        user_id: ID пользователя
        session: Сессия базы данных
        resume: Резюме пользователя
        custom_prompt: Кастомный промпт (для типа CUSTOM)

    Returns:
        Кортеж (результат_анализа, описание_типа_анализа)

    Raises:
        VacancyNotFoundError: Если вакансия не найдена
    """
    # Получаем вакансию (проверяем что она связана с пользователем)
    vacancy = await session.scalar(
        select(VacancyModel)
        .join(UserVacanciesModel)
        .where(
            UserVacanciesModel.user_id == user_id,
            VacancyModel.id == vacancy_id,
            VacancyModel.is_active.is_(True),
        )
    )

    if vacancy is None:
        raise VacancyNotFoundError(f"Вакансия {vacancy_id} не найдена")

    if not vacancy.description:
        raise VacancyNotFoundError(f"У вакансии {vacancy_id} отсутствует описание")

    # Формируем контент для анализа
    content = {"description": vacancy.description}

    result = await analyze_vacancy(
        content=content, llm=llm, analysis_type=analysis_type, resume=resume, custom_prompt=custom_prompt
    )
    logger.info(f"Анализ {analysis_type.value} вакансии {str(vacancy_id)} успешно завершён")
    return result, analysis_type.description
