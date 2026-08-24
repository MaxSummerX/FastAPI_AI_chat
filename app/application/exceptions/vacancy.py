class VacancyNotFoundError(Exception):
    """Вакансия не найдена."""

    pass


class VacancyFetchError(Exception):
    """Ошибка при загрузке вакансии с hh.ru (сеть/парсинг/анти-бот)."""

    pass


class VacancyImportError(Exception):
    """Ошибка пайплайна импорта вакансий (фильтрация, файлы)."""

    pass


class InvalidVacancyCursorError(Exception):
    """Невалидный курсор пагинации вакансий."""

    pass


class AnalysisAlreadyExistsError(Exception):
    """Анализ данного типа уже существует для вакансии пользователя."""

    pass


class AnalysisNotFoundError(Exception):
    """Анализ не найден или принадлежит другому пользователю."""

    pass


class ResumeRequiredError(Exception):
    """Резюме пользователя не загружено."""

    pass


class ResumeTooShortError(Exception):
    """Резюме пользователя слишком короткое."""

    pass
