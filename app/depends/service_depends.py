from fastapi import Depends
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.dependencies import get_db
from app.services.document_service import DocumentService
from app.services.headhunter.headhunter_client import get_hh_client
from app.services.headhunter.vacancy_status import VacancyArchiveSync


REQUEST_DELAY_ARCHIVE: float = 2.0
SEMAPHORE_COUNT: int = 2


def get_document_service(db: AsyncSession = Depends(get_db)) -> DocumentService:
    """Фабрика для создания DocumentService через Dependency Injection."""
    return DocumentService(db)


async def get_vacancy_archive_sync(
    db: AsyncSession = Depends(get_db),
    hh_client: AsyncClient = Depends(get_hh_client),
) -> VacancyArchiveSync:
    """
    Фабрика для создания VacancyArchiveSync через Dependency Injection.

    Args:
        db: Асинхронная сессия БД
        hh_client: HTTP клиент для запросов к hh.ru

    Returns:
        VacancyArchiveSync: Сервис для синхронизации архивных статусов вакансий
    """
    return VacancyArchiveSync(
        db_session=db,
        hh_client=hh_client,
        semaphore_count=SEMAPHORE_COUNT,
        request_delay=REQUEST_DELAY_ARCHIVE,
    )


# TODO: Добавить фабрики для других сервисов
