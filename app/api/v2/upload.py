from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile, status
from loguru import logger

from app.auth.dependencies import get_current_user
from app.enum.providers import ImportedProvider
from app.models.users import User as UserModel
from app.tools.upload.upload_conversations import upload_conversations_other_provider


router = APIRouter(prefix="/upload", tags=["Imports_V2"])


@router.post("/conversations_import/", status_code=status.HTTP_201_CREATED)
async def conversations_import(
    provider: ImportedProvider,
    background_tasks: BackgroundTasks,
    current_user: UserModel = Depends(get_current_user),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """
    Асинхронно сохраняет загруженный файл на диск и сохраняет беседы в бд от соответствующего провайдера
    """
    logger.info(f"Вызовы импорта бесед для пользователя {current_user.id}")
    return await upload_conversations_other_provider(
        provider=provider,
        background_tasks=background_tasks,
        user_id=current_user.id,
        file=file,
    )
