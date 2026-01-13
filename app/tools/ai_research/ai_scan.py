import asyncio
from typing import Any, cast
from uuid import UUID

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.configs.llm_config import researcher_llm_config
from app.llms.openai import AsyncOpenAILLM
from app.models.vacancies import Vacancy as VacancyModel
from app.prompts.prompts_for_analysis import PREPARATION_PROMPT


llm = AsyncOpenAILLM(researcher_llm_config)


async def analyze_vacancy_from_db(
    vacancy_id: UUID,
    user_id: UUID,
    session: AsyncSession,
) -> str | dict[str, Any] | None:
    try:
        stmt = await session.scalars(
            select(VacancyModel).where(
                VacancyModel.id == vacancy_id, VacancyModel.user_id == user_id, VacancyModel.is_active.is_(True)
            )
        )
        result = stmt.first()
        request = [
            {"role": "system", "content": f"{str(PREPARATION_PROMPT)}"},
            {"role": "user", "content": f"{str(result.description)}"},
        ]
        return cast(str | dict[str, Any], await llm.generate_response(request))

    except Exception as e:
        logger.error(f"Ошибка при анализе вакансии: {e}")
        return None


async def analyze_vacancy(
    message: str,
) -> str | dict[str, Any] | None:
    try:
        request = [
            {"role": "system", "content": f"{str(PREPARATION_PROMPT)}"},
            {"role": "user", "content": f"{message}"},
        ]
        result = cast(str | dict[str, Any] | None, await llm.generate_response(request))
        return result
    except Exception as e:
        logger.error(f"Ошибка при анализе вакансии: {e}")
        return None


async def ai_response_with_semaphore(
    index: int,
    message: str,
    semaphore: asyncio.Semaphore,
) -> str | dict[str, Any] | None:
    """Выделяем канал для запроса"""
    async with semaphore:
        await asyncio.sleep(index * 0.1)
        try:
            request = [
                {"role": "system", "content": f"{str(PREPARATION_PROMPT)}"},
                {"role": "user", "content": f"{message}"},
            ]
            result = await llm.generate_response(request)
            return result
        except Exception as e:
            logger.error(f"Ошибка при выполнении запроса {e}")
            return None


async def ai_response_gather(messages: list[str], connect: int) -> list[str | dict[str, Any] | None]:
    """Объединяем запросы в пул"""
    semaphore = asyncio.Semaphore(connect)

    tasks = [ai_response_with_semaphore(i, message, semaphore) for i, message in enumerate(messages)]

    result = await asyncio.gather(*tasks)
    return result
