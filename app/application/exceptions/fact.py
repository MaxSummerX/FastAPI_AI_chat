class FactNotFoundException(Exception):
    """Факт не найден"""

    pass


class UserProvidedException(Exception):
    """Факт не был создан пользователем (нельзя редактировать/удалять)"""

    pass
