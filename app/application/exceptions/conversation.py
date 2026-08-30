from app.application.exceptions.base import BaseAppException


class ConversationNotFoundError(BaseAppException):
    """Исключение, возникающее когда документ не найден или недоступен пользователю."""

    pass
