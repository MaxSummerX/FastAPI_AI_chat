import asyncio
import json
import os
from pathlib import Path
from typing import Any

import aiofiles
from loguru import logger


async def save_conversation_async(conversation: dict[str, Any], output_dir: str, semaphore: asyncio.Semaphore) -> bool:
    """
    Асинхронно сохраняет один диалог в файл

    Args:
        conversation: объект диалога
        output_dir: директория для сохранения
        semaphore: семафор для ограничения одновременных операций

    Returns:
        bool: True если успешно сохранено
    """
    uuid = conversation.get("id")
    if not uuid:
        return False

    async with semaphore:  # Ограничиваем количество одновременных записей
        try:
            filename = f"{uuid}.json"
            filepath = Path(output_dir) / filename

            # Асинхронная запись файла
            async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
                json_str = json.dumps(conversation, ensure_ascii=False, indent=2)
                await f.write(json_str)

            logger.info(f"Сохранен: {filename}")
            return True

        except Exception as e:
            logger.error(f"Ошибка сохранения {uuid}: {e}")
            return False


async def process_conversations_stream(
    input_file: str, output_dir: str, skip_empty: bool = True, max_concurrent_files: int = 10
) -> None:
    """
    Асинхронно обрабатывает файл с диалогами, используя потоковую обработку

    Args:
        input_file: путь к исходному .json файлу
        output_dir: директория для сохранения отдельных файлов
        skip_empty: пропускать ли пустые диалоги
        max_concurrent_files: максимальное количество одновременных операций записи
    """
    # Создаем выходную директорию
    await asyncio.to_thread(os.makedirs, output_dir, exist_ok=True)

    # Семафор для ограничения одновременных файловых операций
    semaphore = asyncio.Semaphore(max_concurrent_files)

    try:
        # Асинхронное чтение файла
        async with aiofiles.open(input_file, encoding="utf-8") as f:
            content = await f.read()

        # Парсинг JSON (это CPU операция, но быстрая)
        conversations = json.loads(content)

        logger.info(f"Загружено {len(conversations)} диалогов")

        saved_count = 0
        skipped_empty = 0
        skipped_no_uuid = 0

        # Создаем задачи для сохранения файлов
        save_tasks = []

        for conversation in conversations:
            uuid = conversation.get("id")
            if not uuid:
                skipped_no_uuid += 1
                logger.info("Пропущен диалог без UUID")
                continue

            # Создаем задачу для асинхронного сохранения
            task = asyncio.create_task(save_conversation_async(conversation, output_dir, semaphore))
            save_tasks.append(task)

        # Ждем завершения всех задач сохранения
        results = await asyncio.gather(*save_tasks, return_exceptions=True)

        # Подсчитываем успешные сохранения
        for result in results:
            if result is True:
                saved_count += 1
            elif isinstance(result, Exception):
                logger.error(f"Ошибка при сохранении: {result}")

        logger.info(f"Готово! Сохранено: {saved_count} файлов")
        if skip_empty:
            logger.info(f"Пропущено пустых диалогов: {skipped_empty}")
        if skipped_no_uuid > 0:
            logger.info(f"Пропущено диалогов без UUID: {skipped_no_uuid}")
        logger.info(f"Файлы сохранены в директорию '{output_dir}'")

        # Асинхронное удаление исходного файла
        await asyncio.to_thread(os.remove, input_file)

    except json.JSONDecodeError as e:
        logger.error(f"Ошибка JSON: {e}")
        raise
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        raise


async def split_conversations_async(
    input_file: str,
    output_dir: str,
    skip_empty: bool = True,
    max_concurrent_files: int = 10,
    use_streaming: bool = False,
) -> None:
    """
    Асинхронная версия функции split_conversations

    Args:
        input_file: путь к исходному .json файлу
        output_dir: директория для сохранения отдельных файлов
        skip_empty: пропускать ли пустые диалоги
        max_concurrent_files: максимальное количество одновременных операций записи
        use_streaming: использовать ли потоковую обработку для больших файлов
    """
    logger.info(f"Начало обработки файла: {input_file}")

    # Проверяем существование файла
    if not await asyncio.to_thread(os.path.exists, input_file):
        raise FileNotFoundError(f"Файл не найден: {input_file}")

    # Проверяем размер файла для выбора стратегии обработки
    file_size = await asyncio.to_thread(os.path.getsize, input_file)
    logger.info(f"Размер файла: {file_size / 1024 / 1024:.2f} MB")

    if use_streaming or file_size > 50 * 1024 * 1024:  # Если файл больше 50MB
        logger.info("Используется потоковая обработка")
        await process_conversations_stream(input_file, output_dir, skip_empty, max_concurrent_files)
    else:
        logger.info("Используется стандартная обработка")
        await process_conversations_stream(input_file, output_dir, skip_empty, max_concurrent_files)
