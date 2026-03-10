from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.depends.db_depends import get_async_postgres_db
from app.services.document_service import DocumentService


def get_document_service(db: AsyncSession = Depends(get_async_postgres_db)) -> DocumentService:
    """Фабрика для создания DocumentService через Dependency Injection."""
    return DocumentService(db)


# TODO: Добавить фабрики для других сервисов
