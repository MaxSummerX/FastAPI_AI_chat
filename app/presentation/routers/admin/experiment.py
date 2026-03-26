from fastapi import APIRouter, BackgroundTasks, Depends, status

from app.depends.service_depends import get_vacancy_archive_sync
from app.services.headhunter.vacancy_status import VacancyArchiveSync


router = APIRouter(prefix="/experiment")


@router.patch("/sync-archive", status_code=status.HTTP_200_OK, summary="Синхронизировать статусы архивации вакансий")
async def sync_vacancies(
    background_tasks: BackgroundTasks,
    service: VacancyArchiveSync = Depends(get_vacancy_archive_sync),
) -> None:
    """
    Запускает фоновую синхронизацию статусов архивации вакансий с hh.ru.

    Операция выполняется асинхронно, ответ возвращается немедленно.
    """
    background_tasks.add_task(service.sync_archive_statuses)
