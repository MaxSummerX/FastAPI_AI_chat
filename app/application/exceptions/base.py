"""Базовые исключения приложения."""


class BaseAppException(Exception):
    """Базовое исключение приложения.

    Все пользовательские исключения должны наследоваться от этого класса.
    Позволяет единообразно обрабатывать ошибки в приложении.
    """

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        """Инициализация исключения.

        Args:
            message: Сообщение об ошибке
            details: Дополнительные детали для логирования/дебага
        """
        self.message = message
        self.details = details or {}
        super().__init__(message)
