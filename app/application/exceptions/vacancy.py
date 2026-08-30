from app.application.exceptions.base import BaseAppException


class VacancyNotFoundError(BaseAppException):
    """Вакансия не найдена."""

    pass


class VacancyFetchError(BaseAppException):
    """Ошибка при загрузке вакансии с hh.ru (сеть/парсинг/анти-бот)."""

    pass


class VacancyImportError(BaseAppException):
    """Ошибка пайплайна импорта вакансий (фильтрация, файлы)."""

    pass


class InvalidVacancyCursorError(BaseAppException):
    """Невалидный курсор пагинации вакансий."""

    pass


class AnalysisAlreadyExistsError(BaseAppException):
    """Анализ данного типа уже существует для вакансии пользователя."""

    pass


class AnalysisNotFoundError(BaseAppException):
    """Анализ не найден или принадлежит другому пользователю."""

    pass


class ResumeRequiredError(BaseAppException):
    """Резюме пользователя не загружено."""

    pass


class ResumeTooShortError(BaseAppException):
    """Резюме пользователя слишком короткое."""

    pass
