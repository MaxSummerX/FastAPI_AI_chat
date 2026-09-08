from fastapi import APIRouter, BackgroundTasks, Depends, status
from httpx import AsyncClient

from app.infrastructure.hh.headhunter_client import get_hh_client
from app.presentation.background import bg_sync_archive_statuses


router = APIRouter(prefix="/experiment")


@router.patch("/sync-archive", status_code=status.HTTP_200_OK, summary="Синхронизировать статусы архивации вакансий")
async def sync_vacancies(
    background_tasks: BackgroundTasks,
    hh_client: AsyncClient = Depends(get_hh_client),
) -> None:
    """
    Запускает фоновую синхронизацию статусов архивации вакансий с hh.ru.

    Операция выполняется асинхронно, ответ возвращается немедленно.
    """
    background_tasks.add_task(bg_sync_archive_statuses, hh_client)
