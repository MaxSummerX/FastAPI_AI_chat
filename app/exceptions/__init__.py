"""Исключения приложения."""

from app.exceptions.exceptions import (
    InvalidAnalysisTypeError,
    LLMError,
    LLMGenerationError,
    NotFoundError,
    PromptNotFoundError,
    UserNotFoundError,
    VacancyNotFoundError,
    ValidationError,
)


__all__ = [
    "NotFoundError",
    "PromptNotFoundError",
    "VacancyNotFoundError",
    "UserNotFoundError",
    "ValidationError",
    "InvalidAnalysisTypeError",
    "LLMError",
    "LLMGenerationError",
]
