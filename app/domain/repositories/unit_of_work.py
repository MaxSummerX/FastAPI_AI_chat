"""Абстракция Unit of Work: единая точка коммита составных транзакций."""

from typing import Protocol


class IUnitOfWork(Protocol):
    """
    Управляет границей транзакции для операций из нескольких шагов.
    """

    async def commit(self) -> None:
        """Зафиксировать транзакцию."""
        ...

    async def rollback(self) -> None:
        """Откатить транзакцию."""
        ...
