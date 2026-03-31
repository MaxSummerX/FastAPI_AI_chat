"""
Dependency injection для LLM инстансов.

Предоставляет асинхронные генераторы для работы с LLM
в соответствии с паттерном FastAPI dependency injection.
"""

from collections.abc import AsyncGenerator

from app.infrastructure.llms.config import base_config_for_llm, researcher_llm_config
from app.infrastructure.llms.openai import AsyncOpenAILLM


async def get_researcher_llm() -> AsyncGenerator[AsyncOpenAILLM]:
    """
    Предоставляет инстанс LLM для AI-исследования.

    Использует researcher_llm_config для конфигурации.
    Создаёт новый инстанс для каждого запроса (stateless).

    Yields:
        AsyncOpenAILLM: Инстанс LLM для выполнения запросов

    Example:
        @router.get("/analyze")
        async def analyze(
            llm: Annotated[AsyncOpenAILLM, Depends(get_researcher_llm)]
        ):
            result = await llm.generate_response(messages)
    """
    llm = AsyncOpenAILLM(researcher_llm_config)
    yield llm


async def get_base_llm() -> AsyncGenerator[AsyncOpenAILLM]:
    """
    Предоставляет базовый инстанс LLM для обработки сообщений.

    Использует base_config_for_llm для конфигурации.
    Создаёт новый инстанс для каждого запроса (stateless).

    Yields:
        AsyncOpenAILLM: Инстанс LLM для выполнения запросов

    Example:
        @router.post("/stream")
        async def stream(
            llm: Annotated[AsyncOpenAILLM, Depends(get_base_llm)]
        ):
            result = await llm.generate_stream_response(messages)
    """
    llm = AsyncOpenAILLM(base_config_for_llm)
    yield llm


_llm_instance: AsyncOpenAILLM | None = None


async def get_base_llm_single() -> AsyncGenerator[AsyncOpenAILLM]:
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = AsyncOpenAILLM(base_config_for_llm)
    yield _llm_instance
