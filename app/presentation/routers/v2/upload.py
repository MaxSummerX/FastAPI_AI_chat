from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from loguru import logger

from app.application.services.upload_service import UploadService
from app.domain.enums.provider import ImportedProvider
from app.domain.models.user import User as UserModel
from app.infrastructure.upload.file_storage import (
    build_paths,
    save_file_with_validation,
    validate_file_extension,
    validate_mime_type,
)
from app.presentation.dependencies import get_current_user, get_upload_service


router = APIRouter(prefix="/upload", tags=["Imports_V2"])


@router.post(
    "/conversations_import",
    status_code=status.HTTP_201_CREATED,
    summary="Импорт диалогов из Claude.ai или GPT",
)
async def conversations_import(
    provider: ImportedProvider,
    background_tasks: BackgroundTasks,
    current_user: UserModel = Depends(get_current_user),
    upload_service: UploadService = Depends(get_upload_service),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """ """
    logger.info(f"Вызовы импорта бесед для пользователя {current_user.id}")
    if not file.filename or not file.content_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename and Content-Type required")

    validate_file_extension(file.filename)
    validate_mime_type(file.content_type)

    file_path, split_dir = build_paths(current_user.id)
    file_size = await save_file_with_validation(file, file_path)

    try:
        if provider == ImportedProvider.GPT:
            background_tasks.add_task(
                upload_service.import_from_gpt,
                current_user.id,
                provider.value,
                file_path,
                split_dir,
            )
        elif provider == ImportedProvider.CLAUDE:
            background_tasks.add_task(
                upload_service.import_from_claude,
                current_user.id,
                provider.value,
                file_path,
                split_dir,
            )

        return {
            "filename": file.filename,
            "content_type": file.content_type,
            "size_bytes": file_size,
            "size_mb": round(file_size / (1024 * 1024), 2),
            "message": "processing",
            "provider": provider.value,
        }

    except Exception as e:
        logger.error(f"Unexpected error при загрузке файла {file.filename}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File upload failed",
        ) from None
