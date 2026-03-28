class LLMError(Exception):
    """Базовый класс для ошибок LLM."""

    pass


class LLMGenerationError(LLMError):
    """Ошибка генерации ответа LLM."""

    pass
