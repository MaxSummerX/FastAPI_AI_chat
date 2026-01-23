"""
Dependency injection для LLM инстансов.

Предоставляет асинхронные генераторы для работы с LLM
в соответствии с паттерном FastAPI dependency injection.
"""

from collections.abc import AsyncGenerator

from app.configs.llm_config import researcher_llm_config
from app.llms.openai import AsyncOpenAILLM


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
