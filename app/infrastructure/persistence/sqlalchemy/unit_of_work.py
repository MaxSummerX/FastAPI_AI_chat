"""SQLAlchemy реализация Unit of Work поверх AsyncSession."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.unit_of_work import IUnitOfWork


class SqlAlchemyUnitOfWork(IUnitOfWork):
    """SQLAlchemy реализация Unit of Work."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def commit(self) -> None:
        """Зафиксировать транзакцию."""
        await self._session.commit()

    async def rollback(self) -> None:
        """Откатить транзакцию."""
        await self._session.rollback()
