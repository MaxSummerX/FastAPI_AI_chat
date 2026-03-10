"""Базовые исключения приложения."""


class BaseAppException(Exception):
    """Базовое исключение приложения.

    Все пользовательские исключения должны наследоваться от этого класса.
    Позволяет единообразно обрабатывать ошибки в приложении.
    """

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        """Инициализация исключения.

        Args:
            message: Сообщение об ошибке
            details: Дополнительные детали для логирования/дебага
        """
        self.message = message
        self.details = details or {}
        super().__init__(message)


# =============================================================================
# Исключения для не найденных сущностей (404)
# =============================================================================


class NotFoundError(BaseAppException):
    """Сущность не найдена."""

    pass


class PromptNotFoundError(NotFoundError):
    """Промпт не найден или недоступен."""

    pass


class VacancyNotFoundError(NotFoundError):
    """Вакансия не найдена."""

    pass


class UserNotFoundError(NotFoundError):
    """Пользователь не найден."""

    pass


class DocumentNotFoundError(Exception):
    """Исключение, возникающее когда документ не найден или недоступен пользователю."""

    pass


# =============================================================================
# Исключения для ошибок валидации (422)
# =============================================================================


class ValidationError(BaseAppException):
    """Ошибка валидации данных."""

    pass


class InvalidAnalysisTypeError(ValidationError):
    """Неверный тип анализа."""

    pass


# =============================================================================
# Исключения для ошибок LLM
# =============================================================================


class LLMError(BaseAppException):
    """Базовый класс для ошибок LLM."""

    pass


class LLMGenerationError(LLMError):
    """Ошибка генерации ответа LLM."""

    pass


class InvalidCursorError(ValueError):
    """Невалидный формат курсора"""

    pass
