from collections.abc import Callable
from typing import Any

from app.configs.llms.base import BaseLlmConfig


class OpenAIConfig(BaseLlmConfig):
    """
    Класс конфигурации для параметров, специфичных для OpenAI и OpenRouter.
    Наследует от BaseLlmConfig и добавляет настройки, специфичные для OpenAI.
    Инициализируйте конфигурацию OpenAI.

    Args:
        openai_base_url: Базовый URL-адрес API OpenAI, по умолчанию — None
        models: Список моделей для OpenRouter, по умолчанию — None
        route: Список моделей для OpenRouter, по умолчанию — None
        openrouter_base_url: Базовый URL OpenRouter, по умолчанию — None
        site_url: URL-адрес сайта для OpenRouter, по умолчанию — None
        app_name: Имя приложения для OpenRouter, по умолчанию — None
        store: Флаг, разрешающий OpenAI сохранять ваши диалоги. по умолчанию — False
    """

    openai_base_url: str | None = None
    models: list[str] | None = None
    route: str | None = "fallback"
    openrouter_base_url: str | None = None
    site_url: str | None = None
    app_name: str | None = None
    store: bool = False
    response_callback: Callable[[Any, dict, dict], None] | None = None
