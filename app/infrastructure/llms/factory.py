"""
Фабрики для создания LLM инстансов и сервисов.

Используются в presentation/dependencies.py для внедрения через Depends().
"""

from app.domain.services import ILLMService
from app.infrastructure.llms.config import analysis_llm_config
from app.infrastructure.llms.configs.openai import OpenAIConfig
from app.infrastructure.llms.openai import AsyncOpenAILLM
from app.infrastructure.llms.openai_llm_service import OpenAILLMService


def create_analysis_llm() -> AsyncOpenAILLM:
    """Создаёт LLM инстанс для анализа вакансий (analysis_llm_config)."""
    return AsyncOpenAILLM(analysis_llm_config)


def create_llm_service(config: OpenAIConfig) -> ILLMService:
    """Создаёт LLM сервис, реализующий ILLMService, для application layer."""
    llm = AsyncOpenAILLM(config)
    return OpenAILLMService(llm)
