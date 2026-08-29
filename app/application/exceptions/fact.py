class FactNotFoundException(Exception):
    """Факт не найден"""

    pass


class UserProvidedException(Exception):
    """Факт не был создан пользователем (нельзя редактировать/удалять)"""

    pass


class FactCreationException(Exception):
    """Ошибка создания факта во внешней системе памяти (mem0ai/Qdrant)."""

    pass
