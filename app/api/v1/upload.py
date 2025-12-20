import os
from pathlib import Path
from typing import Any

import aiofiles
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status

from app.auth.dependencies import get_current_user
from app.models.users import User as UserModel
from app.utils.claude_history_converter import convert


router_v1 = APIRouter(prefix="/upload", tags=["Imports"])

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
CONVERSATION_DIR = BASE_DIR / "temp_files"

# Создаем директорию для файлов, если её нет
os.makedirs(CONVERSATION_DIR, exist_ok=True)

# --- Конфигурация для валидации размера ---
MAX_FILE_SIZE_MB = 100
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
# --- Конфигурация для валидации типа ---
ALLOWED_MIME_TYPES = [
    "application/json",
]
ALLOWED_FILE_EXTENSIONS = [".json"]


@router_v1.post("/conversations_import/")
async def conversations_import(
    provider: str,
    background_tasks: BackgroundTasks,
    current_user: UserModel = Depends(get_current_user),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """
    Асинхронно сохраняет загруженный файл на диск, читая его по частям.
    """
    current_size = 0  # Переменная для отслеживания текущего прочитанного размера
    chunk_size = 1024 * 1024  # Размер чанка для чтения (1 МБ)
    filename_lower = file.filename.lower()
    file_extension = os.path.splitext(filename_lower)[1]

    if file_extension not in ALLOWED_FILE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension: '{file_extension}'. Only {', '.join(ALLOWED_FILE_EXTENSIONS)} are allowed.",
        )

    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: '{file.content_type}'. Only {', '.join(ALLOWED_MIME_TYPES)} are allowed.",
        )

    original_filename = f"user_{current_user.id}.json"
    original_filename_location = CONVERSATION_DIR / original_filename

    try:
        # Открываем файл для асинхронной записи на диск
        async with aiofiles.open(original_filename_location, "wb") as out_file:
            # Читаем файл по частям
            while content := await file.read(chunk_size):
                current_size += len(content)

                # --- Логика валидации размера ---
                if current_size > MAX_FILE_SIZE_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        # Статус 413 указывает на слишком большой размер сущности
                        detail=f"File too large. Max size is {MAX_FILE_SIZE_MB}MB.",
                    )

                await out_file.write(content)

        split_dialogs_dir = f"dialogs_user_{current_user.id}"
        split_dialogs_location = CONVERSATION_DIR / split_dialogs_dir

        # Создаём фоновую задачу для выделения диалогов и их записи в бд
        background_tasks.add_task(
            convert,
            user_id=current_user.id,
            provider=provider,
            path=split_dialogs_location,
            input_file=str(original_filename_location),
            output_dir=str(split_dialogs_location),
        )

        return {
            "filename": file.filename,
            "content_type": file.content_type,
            "size_bytes": current_size,
            "message": "File imported",
        }

    except HTTPException:
        if os.path.exists(original_filename_location):
            os.remove(original_filename_location)
        raise

    except Exception as e:
        # Общая обработка других возможных ошибок (например, проблем с диском)
        if os.path.exists(original_filename_location):
            os.remove(original_filename_location)  # Удаляем неполный файл
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during file upload: {e}",
        ) from e
