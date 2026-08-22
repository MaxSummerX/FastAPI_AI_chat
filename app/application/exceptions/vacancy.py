class VacancyNotFoundError(Exception):
    """Вакансия не найдена."""

    pass


class InvalidVacancyCursorError(Exception):
    """Невалидный курсор пагинации вакансий."""

    pass


class AnalysisAlreadyExistsError(Exception):
    """Анализ данного типа уже существует для вакансии пользователя."""

    pass


class ResumeRequiredError(Exception):
    """Резюме пользователя не загружено."""

    pass


class ResumeTooShortError(Exception):
    """Резюме пользователя слишком короткое."""

    pass
