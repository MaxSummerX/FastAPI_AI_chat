class AnalysisError(Exception):
    """Базовый класс для ошибок анализа."""

    pass


class VacancyNotFoundError(AnalysisError):
    """Вакансия не найдена."""

    pass


class UserNotFoundError(AnalysisError):
    """Пользователь не найден."""

    pass


class LLMError(AnalysisError):
    """Ошибка при обращении к LLM."""

    pass


class InvalidAnalysisTypeError(AnalysisError):
    """Неверный тип анализа."""

    pass
