from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enum.analysis import AnalysisType
from app.llms.openai import AsyncOpenAILLM
from app.models.users import User as UserModel
from app.models.vacancies import Vacancy as VacancyModel
from app.tools.ai_research.exceptions import (
    InvalidAnalysisTypeError,
    LLMError,
    UserNotFoundError,
    VacancyNotFoundError,
)
from app.tools.ai_research.llm import _call_llm_with_retry
from app.tools.ai_research.prompts import prompt_choice


async def analyze_vacancy_from_db(
    llm: AsyncOpenAILLM,
    vacancy_id: UUID,
    analysis_type: AnalysisType,
    user_id: UUID,
    session: AsyncSession,
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
        custom_prompt: Кастомный промпт (для типа CUSTOM)

    Returns:
        Кортеж (результат_анализа, описание_типа_анализа)

    Raises:
        VacancyNotFoundError: Если вакансия не найдена
        UserNotFoundError: Если пользователь не найден
        InvalidAnalysisTypeError: Если тип анализа не поддерживается
        LLMError: Если не удалось получить ответ от LLM
    """
    # Получаем вакансию
    vacancy = await session.scalar(
        select(VacancyModel).where(
            VacancyModel.id == vacancy_id, VacancyModel.user_id == user_id, VacancyModel.is_active.is_(True)
        )
    )

    if vacancy is None:
        raise VacancyNotFoundError(f"Вакансия {vacancy_id} не найдена")

    if not vacancy.description:
        raise VacancyNotFoundError(f"У вакансии {vacancy_id} отсутствует описание")

    # Получаем промпт для анализа
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

    # Формируем контент для анализа
    content = vacancy.description

    # Добавляем резюме если нужно
    if need_resume:
        user = await session.scalar(select(UserModel).where(UserModel.id == user_id))

        if user is None:
            raise UserNotFoundError(f"Пользователь {user_id} не найден")

        if not user.resume:
            logger.warning(f"У пользователя {user_id} отсутствует резюме, анализ может быть неполным")

        resume = user.resume or "Резюме не заполнено"
        content += "\n\n## Резюме кандидата\n" + resume

    # Формируем сообщения для LLM
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": content},
    ]

    # Вызываем LLM с retry
    try:
        llm_result = await _call_llm_with_retry(llm, messages)
        # Преобразуем результат в строку (LLM может вернуть dict для structured output)
        result: str = llm_result if isinstance(llm_result, str) else str(llm_result)
        logger.info(f"Анализ {analysis_type.value} вакансии {vacancy_id} успешно завершён")
        return result, analysis_type.description

    except LLMError:
        raise
    except Exception as e:
        logger.error(f"Неожиданная ошибка при анализе: {e}")
        raise LLMError(f"Неожиданная ошибка при анализе: {e}") from e
