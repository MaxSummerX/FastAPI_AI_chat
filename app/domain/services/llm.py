"""Интерфейсы сервисов LLM для доменного слоя.

Определяет контракт для работы с языковыми моделями через абстракции,
не зависящие от конкретных реализаций (OpenAI, Anthropic, и т.д.).
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable
from typing import Any


class ILLMService(ABC):
    """Интерфейс сервиса для работы с LLM.

    Определяет контракт для генерации текста через языковые модели.
    Реализации должны обеспечивать как обычную, так и потоковую генерацию.
    """

    @abstractmethod
    async def generate_stream_response(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        **kwargs: Any,
    ) -> tuple[AsyncIterator[str], Awaitable[dict[str, Any]]]:
        """Сгенерировать потоковый ответ от LLM.

        Args:
            messages: Список сообщений в формате [{'role': 'user', 'content': 'text'}]
            model: Название модели для генерации (None → дефолтная)
            tools: Список доступных tools для function calling
            tool_choice: Стратегия выбора tools ('auto', 'none', или конкретный tool)
            **kwargs: Дополнительные параметры для LLM

        Returns:
            Кортеж из (итератор токенов, awaitable с финальным ответом)
        """

    @abstractmethod
    async def generate_response(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        **kwargs: Any,
    ) -> str | dict[str, Any]:
        """Сгенерировать ответ от LLM (без потока).

        Args:
            messages: Список сообщений в формате [{'role': 'user', 'content': 'text'}]
            model: Название модели для генерации (None → дефолтная)
            **kwargs: Дополнительные параметры для LLM

        Returns:
            Строка с текстом ответа или dict для структурированного вывода
        """

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Вернуть название модели по умолчанию."""
