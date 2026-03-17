from fastapi import APIRouter, BackgroundTasks, Depends, status

from app.auth.dependencies import get_current_admin_user
from app.depends.service_depends import get_vacancy_archive_sync
from app.models.users import User as UserModel
from app.services.headhunter.vacancy_status import VacancyArchiveSync


router = APIRouter(prefix="/experiment")

TAGS = "Experiments"


@router.patch("/sync-archive", status_code=status.HTTP_200_OK, tags=[TAGS], summary="")
async def sync_vacancies(
    background_tasks: BackgroundTasks,
    current_user: UserModel = Depends(get_current_admin_user),
    service: VacancyArchiveSync = Depends(get_vacancy_archive_sync),
) -> None:

    background_tasks.add_task(service.sync_archive_statuses)
