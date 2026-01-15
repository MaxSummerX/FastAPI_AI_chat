import os
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import BackgroundTasks, File, HTTPException, UploadFile, status
from loguru import logger

from app.enum.providers import ImportedProvider
from app.tools.upload.upload_tools import save_file_with_validation, validate_file_extension, validate_mime_type
from app.utils.claude_history_converter import convert
from app.utils.gpt_converter import convert_gtp


SUCCESS_FILE_UPLOADED = "File successfully uploaded"

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
CONVERSATION_DIR = BASE_DIR / "temp_files"

os.makedirs(CONVERSATION_DIR, exist_ok=True)


async def upload_conversations_other_provider(
    user_id: UUID,
    provider: ImportedProvider,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    logger.info(f"Попытка загрузки файла: user_id={user_id}, provider={provider.value}, filename={file.filename}")
    validate_file_extension(file.filename)
    validate_mime_type(file.content_type)

    # Формируем путь для сохранения
    original_filename = f"user_{user_id}.json"
    original_filename_location = CONVERSATION_DIR / original_filename

    try:
        # Сохраняем файл с валидацией размера
        file_size = await save_file_with_validation(file, original_filename_location)

        # Формируем путь для разбиённых диалогов
        split_dialogs_dir = f"dialogs_user_{user_id}"
        split_dialogs_location = CONVERSATION_DIR / split_dialogs_dir
        os.makedirs(split_dialogs_location, exist_ok=True)

        if provider == ImportedProvider.GPT:
            logger.info(f"Запуск фоновой задачи для импорта GPT диалогов: user_id={user_id}")
            background_tasks.add_task(
                convert_gtp,
                user_id=user_id,
                provider=provider.value,  # Передаём строковое значение
                path=split_dialogs_location,
                input_file=str(original_filename_location),
                output_dir=str(split_dialogs_location),
            )

        elif provider == ImportedProvider.CLAUDE:
            logger.info(f"Запуск фоновой задачи для импорта Claude диалогов: user_id={user_id}")
            background_tasks.add_task(
                convert,
                user_id=user_id,
                provider=provider.value,  # Передаём строковое значение
                path=split_dialogs_location,
                input_file=str(original_filename_location),
                output_dir=str(split_dialogs_location),
            )

        return {
            "filename": file.filename,
            "content_type": file.content_type,
            "size_bytes": file_size,
            "size_mb": round(file_size / (1024 * 1024), 2),
            "message": SUCCESS_FILE_UPLOADED,
            "provider": provider.value,
        }

    except HTTPException:
        # HTTPException пробрасывается как есть
        raise

    except Exception as e:
        logger.error(f"Unexpected error при загрузке файла {file.filename}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during file upload: {str(e)}",
        ) from e
