class DomainError(Exception):
    """Базовое исключение доменного слоя."""

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        """
        Инициализация исключения.

        Args:
            message: Сообщение об ошибке
            details: Дополнительные детали для логирования/дебага
        """
        self.message = message
        self.details = details or {}
        super().__init__(message)


class UniqueConstraintViolationError(DomainError):
    """Нарушение ограничения уникальности при сохранении в БД."""
