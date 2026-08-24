from fastapi import APIRouter, BackgroundTasks, Depends, status

from app.application.services.vacancy_import_service import VacancyImportService
from app.presentation.dependencies import get_vacancy_import


router = APIRouter(prefix="/experiment")


@router.patch("/sync-archive", status_code=status.HTTP_200_OK, summary="Синхронизировать статусы архивации вакансий")
async def sync_vacancies(
    background_tasks: BackgroundTasks,
    service: VacancyImportService = Depends(get_vacancy_import),
) -> None:
    """
    Запускает фоновую синхронизацию статусов архивации вакансий с hh.ru.

    Операция выполняется асинхронно, ответ возвращается немедленно.
    """
    background_tasks.add_task(service.sync_archive_statuses)
