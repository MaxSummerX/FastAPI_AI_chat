from app.application.exceptions.base import BaseAppException


class FactNotFoundException(BaseAppException):
    """Факт не найден"""

    pass


class UserProvidedException(BaseAppException):
    """Факт не был создан пользователем (нельзя редактировать/удалять)"""

    pass


class FactCreationException(BaseAppException):
    """Ошибка создания факта во внешней системе памяти (mem0ai/Qdrant)."""

    pass
