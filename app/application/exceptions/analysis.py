from app.application.exceptions.base import BaseAppException


class InvalidAnalysisTypeError(BaseAppException):
    """Неверный тип анализа."""

    pass
