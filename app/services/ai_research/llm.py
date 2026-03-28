from typing import Any

from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.application.exceptions.llm import LLMGenerationError
from app.llms.openai import AsyncOpenAILLM


@retry(
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((TimeoutError, ConnectionError)),
    reraise=True,
)
async def _call_llm_with_retry(
    llm: AsyncOpenAILLM,
    messages: list[dict[str, str]],
) -> str | dict[str, Any]:
    """
    Вызывает LLM с автоматическим retry при транзиентных ошибках.

    Retry только на TimeoutError / ConnectionError с экспоненциальным backoff.
    LLMGenerationError (пустой ответ, бизнес-логика) — не ретраится, пробрасывается сразу.

    Args:
        llm: Инстанс LLM (получается через dependency injection)
        messages: Сообщения для LLM в формате OpenAI

    Returns:
        Текстовый ответ от LLM или dict (для structured output)

    Raises:
        LLMGenerationError: Пустой ответ или исчерпаны все попытки
    """
    try:
        result = await llm.generate_response(messages)

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
        raise LLMGenerationError(f"Не удалось получить ответ от LLM: {e}") from e
