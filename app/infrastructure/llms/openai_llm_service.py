"""
OpenAI реализация сервиса LLM для infrastructure layer.

Адаптер над AsyncOpenAILLM, реализующий интерфейс ILLMService
для использования в application layer. Следует принципам
dependency inversion — зависит от абстракции доменного слоя.
"""

from collections.abc import AsyncIterator, Awaitable
from typing import Any

from app.domain.services import ILLMService
from app.infrastructure.llms.openai import AsyncOpenAILLM


class OpenAILLMService(ILLMService):
    """
    OpenAI сервис языковых моделей.

    Адаптер над AsyncOpenAILLM для использования в application layer.
    Реализует интерфейс ILLMService, позволяя менять low-level реализацию
    без изменения бизнес-логики.
    """

    def __init__(self, llm: AsyncOpenAILLM) -> None:
        """
        Инициализирует сервис LLM.

        Args:
            llm: Low-level реализация AsyncOpenAILLM
        """
        self._llm = llm
        self.config = llm.config

    async def generate_stream_response(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        **kwargs: Any,
    ) -> tuple[AsyncIterator[str], Awaitable[dict[str, Any]]]:
        """
        Сгенерировать потоковый ответ от LLM.

        Args:
            messages: Список сообщений в формате [{'role': 'user', 'content': 'text'}]
            model: Название модели (None → дефолтная из конфига)
            tools: Список доступных tools для function calling
            tool_choice: Стратегия выбора tools ('auto', 'none', или конкретный tool)
            **kwargs: Дополнительные параметры для LLM

        Returns:
            Кортеж из (итератор токенов, awaitable с финальным ответом)
        """
        return await self._llm.generate_stream_response(
            messages=messages,
            model=model,
            tools=tools,
            tool_choice=tool_choice,
            **kwargs,
        )

    async def generate_response(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        **kwargs: Any,
    ) -> str | dict[str, Any]:
        """
        Сгенерировать ответ от LLM (без потока).

        Args:
            messages: Список сообщений в формате [{'role': 'user', 'content': 'text'}]
            model: Название модели (None → дефолтная из конфига)
            **kwargs: Дополнительные параметры для LLM

        Returns:
            Строка с текстом ответа или dict для структурированного вывода
        """
        return await self._llm.generate_response(
            messages=messages,
            model=model,
            **kwargs,
        )

    @property
    def default_model(self) -> str:
        """
        Вернуть название модели по умолчанию.

        Returns:
            Название модели из конфига или дефолтное значение
        """
        return self.config.model or "gpt-4o-mini"
