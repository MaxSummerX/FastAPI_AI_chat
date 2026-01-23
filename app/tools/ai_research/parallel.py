import asyncio
from typing import Any

from loguru import logger

from app.llms.openai import AsyncOpenAILLM
from app.prompts.prompts_for_analysis import PREPARATION_PROMPT
from app.tools.ai_research.exceptions import LLMError
from app.tools.ai_research.llm import _call_llm_with_retry


async def ai_response_with_semaphore(
    llm: AsyncOpenAILLM,
    index: int,
    message: str,
    semaphore: asyncio.Semaphore,
) -> str | dict[str, Any] | None:
    """
    Выполняет одиночный запрос к LLM с ограничением через семафор.

    Args:
        llm: Инстанс LLM (получается через dependency injection)
        index: Индекс запроса (для задержки)
        message: Сообщение для LLM
        semaphore: Семафор для ограничения параллелизма

    Returns:
        Результат от LLM или None при ошибке
    """
    async with semaphore:
        await asyncio.sleep(index * 0.1)
        try:
            request = [
                {"role": "system", "content": str(PREPARATION_PROMPT)},
                {"role": "user", "content": str(message)},
            ]
            result: str | dict[str, Any] = await _call_llm_with_retry(llm, request)
            return result
        except LLMError as e:
            logger.error(f"Ошибка при выполнении запроса {index}: {e}")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка при запросе {index}: {e}")
            return None


async def ai_response_gather(
    llm: AsyncOpenAILLM, messages: list[str], connect: int
) -> list[str | dict[str, Any] | None]:
    """
    Выполняет несколько запросов к LLM параллельно с ограничением.

    Args:
        llm: Инстанс LLM (получается через dependency injection)
        messages: Список сообщений для анализа
        connect: Максимальное количество параллельных запросов

    Returns:
        Список результатов от LLM (None для неудачных запросов)
    """
    semaphore = asyncio.Semaphore(connect)

    tasks = [ai_response_with_semaphore(llm, i, message, semaphore) for i, message in enumerate(messages)]

    result = await asyncio.gather(*tasks)
    # gather возвращает tuple[Any, ...], преобразуем в list для типизации
    return list(result)
