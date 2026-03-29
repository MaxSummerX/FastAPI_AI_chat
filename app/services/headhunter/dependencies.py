"""
Зависимости для сервисов headhunter.

Модуль содержит FastAPI dependency-функции для создания сервисов,
работающих с API hh.ru (синхронизация статусов вакансий).
"""

from fastapi import Depends
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.dependencies import get_db
from app.services.headhunter.headhunter_client import get_hh_client
from app.services.headhunter.vacancy_status import VacancyArchiveSync


# Конфигурация для VacancyArchiveSync
REQUEST_DELAY_ARCHIVE: float = 2.0
SEMAPHORE_COUNT: int = 2


async def get_vacancy_archive_sync(
    db: AsyncSession = Depends(get_db),
    hh_client: AsyncClient = Depends(get_hh_client),
) -> VacancyArchiveSync:
    """
    Фабрика для создания VacancyArchiveSync через Dependency Injection.

    Создаёт сервис для синхронизации архивных статусов вакансий с hh.ru API.
    Использует семафор для ограничения параллельных запросов и задержку
    для предотвращения rate limiting.

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
