from typing import Any

from backoff import expo, on_exception
from loguru import logger

from app.llms.openai import AsyncOpenAILLM
from app.tools.ai_research.exceptions import LLMError


@on_exception(expo, Exception, max_tries=3, max_time=30)
async def _call_llm_with_retry(llm: AsyncOpenAILLM, messages: list[dict[str, str]]) -> str | dict[str, Any]:
    """
    Вызывает LLM с автоматическим retry при ошибках.

    Использует экспоненциальный backoff для повторных попыток.

    Args:
        llm: Инстанс LLM (получается через dependency injection)
        messages: Сообщения для LLM в формате OpenAI

    Returns:
        Текстовый ответ от LLM или dict (для structured output)

    Raises:
        LLMError: Если все попытки завершились неудачно
    """
    try:
        result = await llm.generate_response(messages)

        if not result:
            raise LLMError("LLM вернул пустой ответ")

        return result

    except Exception as e:
        logger.error(f"Ошибка при вызове LLM: {e}")
        raise LLMError(f"Не удалось получить ответ от LLM: {e}") from e
