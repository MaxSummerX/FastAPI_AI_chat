class VacancyNotFoundError(Exception):
    """Вакансия не найдена."""

    pass


class InvalidVacancyCursorError(Exception):
    """Невалидный курсор пагинации вакансий."""

    pass
