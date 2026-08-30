from app.application.exceptions.base import BaseAppException


class LLMError(BaseAppException):
    """Базовый класс для ошибок LLM."""

    pass


class LLMGenerationError(LLMError):
    """Ошибка генерации ответа LLM."""

    pass
