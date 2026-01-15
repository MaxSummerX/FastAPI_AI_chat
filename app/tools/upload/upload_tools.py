import os
from pathlib import Path

import aiofiles
from fastapi import HTTPException, UploadFile, status
from loguru import logger


ALLOWED_UPLOAD_EXTENSIONS = {".json"}
ALLOWED_UPLOAD_MIME_TYPES = {"application/json"}
MAX_UPLOAD_FILE_SIZE_MB = 100
MAX_UPLOAD_FILE_SIZE_BYTES = MAX_UPLOAD_FILE_SIZE_MB * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB - размер чанка для чтения файла


def validate_file_extension(filename: str) -> None:
    """
    Проверяет разрешения файла.
    """
    filename_lower = filename.lower()
    file_extension = os.path.splitext(filename_lower)[1]

    if file_extension not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension: '{file_extension}'. Only {', '.join(ALLOWED_UPLOAD_EXTENSIONS)} are allowed.",
        )


def validate_mime_type(content_type: str) -> None:
    """
    Проверяет MIME тип файла
    """
    if content_type not in ALLOWED_UPLOAD_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: '{content_type}'. Only {', '.join(ALLOWED_UPLOAD_MIME_TYPES)} are allowed.",
        )


async def save_file_with_validation(file: UploadFile, path: Path) -> int:
    """
    Асинхронно сохраняет файл на диск с валидацией размера.
    Читает файл чанками для экономии памяти и проверки размера.
    """
    current_size = 0
    try:
        async with aiofiles.open(path, mode="wb") as out_file:
            while content := await file.read(UPLOAD_CHUNK_SIZE):
                current_size += len(content)

                if current_size > MAX_UPLOAD_FILE_SIZE_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"File too large. Max size is {MAX_UPLOAD_FILE_SIZE_MB}MB.",
                    )
                await out_file.write(content)
        return current_size

    except HTTPException:
        if path.exists():
            os.remove(path)
        raise

    except Exception as e:
        if path.exists():
            os.remove(path)
        logger.error(f"Error saving file to {path}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error saving file: {e}") from e
