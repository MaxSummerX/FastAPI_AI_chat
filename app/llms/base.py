from abc import ABC, abstractmethod
from typing import Any

from app.configs.llms.base import BaseLlmConfig


class LLMBase(ABC):
    """
    Базовый класс для всех поставщиков LLM.
    Обрабатывает общие функции и делегирует логику, специфичную для поставщика, подклассам.
    """

    def __init__(self, config: BaseLlmConfig | dict | None = None):
        """
        Инициализация базового LLM класса.

        Args:
            config: Конфигурация LLM (класс, dict или None для дефолтных значений)

        Raises:
            ValueError: Если конфигурация невалидна
        """
        if config is None:
            self.config = BaseLlmConfig()
        elif isinstance(config, dict):
            # Обработка конфигурации на основе словаря (обратная совместимость)
            self.config = BaseLlmConfig(**config)
        else:
            self.config = config

        # Проверка конфигурации
        self._validate_config()

    def _validate_config(self) -> None:
        """
        Проверка конфигурации.
        Переопределите в подклассах, чтобы добавить проверку, специфичную для поставщика.
        """
        if not hasattr(self.config, "model"):
            raise ValueError("Configuration must have a 'model' attribute")

        if not hasattr(self.config, "api_key") and not hasattr(self.config, "api_key"):
            # Проверьте доступность ключа API через переменную окружения
            # Это будет решаться отдельными поставщиками
            pass

    def _is_reasoning_model(self, model: str) -> bool:
        """
        Проверка, является ли модель reasoning model или GPT-5 серией.

        Args:
            model: Название модели

        Returns:
            True если модель reasoning/GPT-5 типа
        """
        reasoning_models = {
            "o1",
            "o1-preview",
            "o3-mini",
            "o3",
            "gpt-5",
            "gpt-5o",
            "gpt-5o-mini",
            "gpt-5o-micro",
        }

        if model.lower() in reasoning_models:
            return True

        model_lower = model.lower()
        if any(reasoning_model in model_lower for reasoning_model in ["gpt-5", "o1", "o3"]):
            return True

        return False

    def _get_supported_params(self, **kwargs: Any) -> dict[str, Any]:
        """
        Получение параметров, поддерживаемых текущей моделью.
        Фильтрует неподдерживаемые параметры для reasoning моделей.

        Args:
            **kwargs: Дополнительные параметры

        Returns:
            Отфильтрованный словарь параметров
        """
        model = getattr(self.config, "model", "")

        if self._is_reasoning_model(model):
            supported_params = {}

            if "messages" in kwargs:
                supported_params["messages"] = kwargs["messages"]
            if "response_format" in kwargs:
                supported_params["response_format"] = kwargs["response_format"]
            if "tools" in kwargs:
                supported_params["tools"] = kwargs["tools"]
            if "tool_choice" in kwargs:
                supported_params["tool_choice"] = kwargs["tool_choice"]

            return supported_params
        else:
            # Обычные модели поддерживают все параметры
            return self._get_common_params(**kwargs)

    @abstractmethod
    async def generate_response(
        self,
        messages: list[dict[str, str]],
        response_format: str | Any = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        **kwargs: Any,
    ) -> str | dict[str, Any]:
        """
        Асинхронная генерация ответа на основе сообщений.

        Args:
            messages: Список словарей с 'role' и 'content'
            response_format: Формат ответа. Для получения ответа от модели в заданным шаблоном
            tools: Список инструментов, доступных модели
            tool_choice: Метод выбора инструмента
            **kwargs: Дополнительные параметры провайдера

        Returns:
            Сгенерированный ответ (строка или словарь)
        """
        pass

    def _get_common_params(self, **kwargs: Any) -> dict[str, Any]:
        """
        Получение общих параметров для большинства провайдеров.

        Args:
            **kwargs: Дополнительные параметры

        Returns:
            Словарь с общими параметрами
        """
        # Используем model_dump() для извлечения validated данных
        params = {
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "top_p": self.config.top_p,
        }

        # Добавляем provider-специфичные параметры
        params.update(kwargs)

        return params
