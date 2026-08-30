from app.application.exceptions.base import BaseAppException


class PromptNotFoundError(BaseAppException):
    """Промпт не найден или недоступен."""

    pass
