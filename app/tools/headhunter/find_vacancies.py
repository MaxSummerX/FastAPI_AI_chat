"""
Модуль для импорта вакансий с HeadHunter.ru
"""

import asyncio
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import aiofiles
import httpx
from fastapi import HTTPException
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enum.experience import Experience
from app.models.vacancies import Vacancy
from app.tools.headhunter.headhunter_client import (
    HH_CONCURRENT_REQUESTS,
    HH_MAX_PAGES,
    HH_REQUEST_DELAY,
    HHApiEndpoint,
    get_hh_client,
)


BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
TEMP_DIR = BASE_DIR / "temp_files"

# Убедимся что директория существует
TEMP_DIR.mkdir(parents=True, exist_ok=True)


def get_user_vacancy_files(user_id: UUID) -> tuple[Path, Path]:
    """
    Возвращает пути к файлам вакансий для конкретного пользователя.

    Решает проблему: DEFAULT_VACANCIES_FILE и DEFAULT_FILTERED_VACANCIES_FILE
    должны быть для каждого пользователя отдельно, иначе все пользователи
    будут перезаписывать один и тот же файл.

    Args:
        user_id: UUID пользователя

    Returns:
        tuple[Path, Path]: (путь к сырым вакансиям, путь к отфильтрованным)
    """
    user_temp_dir = TEMP_DIR / str(user_id)
    user_temp_dir.mkdir(parents=True, exist_ok=True)

    return (
        user_temp_dir / "vacancies.json",
        user_temp_dir / "filtered_vacancies.json",
    )


async def fetch_full_vacancy(
    vacancy_id: str,
    hh_client: httpx.AsyncClient,
) -> dict[str, Any]:
    """
    Получает полное описание вакансии по ID.

    Args:
        vacancy_id: ID вакансии на hh.ru
        hh_client: HTTP клиент для запросов к API

    Returns:
        dict с полным описанием вакансии

    Raises:
        HTTPException: если вакансия не найдена или произошла ошибка
    """

    try:
        # Формируем URL
        url = HHApiEndpoint.VACANCIES_BY_ID.format(vacancy_id=vacancy_id)

        response = await hh_client.get(url)

        # Проверка статуса
        response.raise_for_status()

        # Возвращаем ответ
        return cast(dict[str, Any], response.json())

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP ошибка: {e.response.status_code}")
        raise HTTPException(status_code=e.response.status_code, detail="Вакансия не найдена") from None

    except Exception as e:
        logger.error(f"Ошибка при загрузке вакансии {vacancy_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка при загрузке описании вакансии: {e}") from None


async def vacancy_create(hh_id: str, query: str, user_id: UUID, hh_client: httpx.AsyncClient) -> Vacancy:
    """
    Создаёт объект Vacancy на основе данных с hh.ru.

    Args:
        hh_id: ID вакансии на hh.ru
        query: Поисковый запрос
        user_id: ID пользователя
        hh_client: HTTP клиент

    Returns:
        Vacancy: Объект вакансии для сохранения в БД
    """

    details = await fetch_full_vacancy(hh_id, hh_client)

    salary = details.get("salary") or {}
    experience = details.get("experience") or {}
    area = details.get("area") or {}
    schedule = details.get("schedule") or {}
    employment = details.get("employment") or {}
    employer = details.get("employer") or {}

    # Парсинг даты публикации из ISO формата
    published_at_str = details.get("published_at")
    published_at = None
    if published_at_str:
        try:
            # Парсим дату в формате ISO 8601 (например: "2026-01-07T11:56:31+0300")
            published_at = datetime.fromisoformat(published_at_str)
        except (ValueError, TypeError) as e:
            logger.warning(f"Не удалось распарсить дату {published_at_str}: {e}")

    return Vacancy(
        user_id=user_id,
        hh_id=hh_id,
        query_request=query,
        title=details.get("name"),
        description=details.get("description"),
        salary_from=salary.get("from"),
        salary_to=salary.get("to"),
        salary_currency=salary.get("currency"),
        salary_gross=salary.get("gross"),
        experience_id=experience.get("id"),
        area_id=area.get("id"),
        area_name=area.get("name"),
        schedule_id=schedule.get("id"),
        employment_id=employment.get("id"),
        employer_id=employer.get("id"),
        employer_name=employer.get("name"),
        hh_url=details.get("alternate_url"),
        apply_url=details.get("apply_alternate_url"),
        is_archived=details.get("archived", False),
        raw_data=details,
        published_at=published_at,
    )


async def vacancies_create(
    query: str,
    user_id: UUID,
    hh_client: httpx.AsyncClient,
    session: AsyncSession,
    input_path: str | Path | None = None,
) -> dict[str, int]:
    """
    Пакетное добавление вакансий в БД из файла.

    Args:
        query: Поисковый запрос
        user_id: ID пользователя
        hh_client: HTTP клиент
        session: SQLAlchemy асинхронная сессия
        input_path: Путь к файлу с вакансиями (по умолчанию из пользовательской директории)

    Returns:
        dict со статистикой:
            - total_found: всего найдено в файле
            - already_exists: уже было в БД
            - new_added: новых добавлено
            - errors: количество ошибок
    """

    if input_path is None:
        _, input_path = get_user_vacancy_files(user_id)

    async with aiofiles.open(input_path, encoding="utf-8") as file:
        content = await file.read()
        vacancies = json.loads(content)

    # Собираем все ID вакансий
    all_ids = [vac.get("id") for vac in vacancies if vac.get("id")]

    # Проверяем какие уже есть в БД
    stmt = select(Vacancy.hh_id).where(Vacancy.hh_id.in_(all_ids))
    result = await session.execute(stmt)
    existing_ids = {row.hh_id for row in result}

    new_ids = set(all_ids) - existing_ids

    logger.info(f"Всего найдено: {len(all_ids)}")
    logger.info(f"Уже в БД: {len(existing_ids)}")
    logger.info(f"Новых для загрузки: {len(new_ids)}")

    vacancies_to_add = []
    error_count = 0

    for hh_id in new_ids:
        try:
            vacancy = await vacancy_create(hh_id, query, user_id, hh_client)
            vacancies_to_add.append(vacancy)
            await asyncio.sleep(HH_REQUEST_DELAY)

        except Exception as e:
            logger.error(f"Ошибка при обработке вакансии {hh_id}: {e}")
            error_count += 1
            continue

    session.add_all(vacancies_to_add)
    await session.commit()
    logger.info("Загрузка вакансий в БД завершена")

    return {
        "total_found": len(all_ids),
        "already_exists": len(existing_ids),
        "new_added": len(vacancies_to_add),
        "errors": error_count,
    }


async def fetch_with_semaphore(
    semaphore: asyncio.Semaphore, client: httpx.AsyncClient, params: dict[str, Any]
) -> dict[str, Any] | None:
    """
    Выполняет запрос с ограничением по количеству одновременных соединений.

    Args:
        semaphore: Семафор для ограничения concurrent requests
        client: HTTP клиент
        params: Параметры запроса

    Returns:
        dict с ответом API или None в случае ошибки
    """
    async with semaphore:
        try:
            url = HHApiEndpoint.VACANCIES
            response = await client.get(url, params=params)
            if response.status_code != 200:
                logger.warning(f"Запрос упал с ошибкой: статус {response.status_code}")
                return None
            logger.info(f"Успешный запрос: страница {params.get('page', 'N/A')}")
            return cast(dict[str, Any], response.json())
        except Exception as e:
            logger.error(f"Ошибка при выполнении запроса {params}: {e}")
            return None


async def fetch_data_gather(
    params: list[dict[str, Any]],
    max_connections: int,
    hh_client: httpx.AsyncClient,
) -> list[dict[str, Any] | None]:
    """
    Объединяет запросы в пул для параллельного выполнения.

    Args:
        params: Список параметров для запросов
        max_connections: Максимальное количество одновременных соединений
        hh_client: HTTP клиент

    Returns:
        list с результатами всех запросов
    """
    semaphore = asyncio.Semaphore(max_connections)
    tasks = [fetch_with_semaphore(semaphore, hh_client, param) for param in params]
    return await asyncio.gather(*tasks)


async def fetch_all_hh_vacancies(
    query: str,
    hh_client: httpx.AsyncClient,
    user_id: UUID,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """
    Загружает асинхронно несколько страниц с вакансиями и сохраняет в файл.
    запрос -> django OR fastapi OR aiohttp OR litestar OR flask

    Args:
        query: Поисковый запрос (например: "django OR fastapi")
        hh_client: HTTP клиент
        user_id: ID пользователя (для определения пути сохранения)
        output_path: Путь для сохранения (по умолчанию из пользовательской директории)

    Returns:
        dict со статистикой:
            - vacancies_count: количество найденных вакансий
            - pages_processed: количество обработанных страниц

    Raises:
        HTTPException: при ошибке загрузки
    """
    if output_path is None:
        output_path, _ = get_user_vacancy_files(user_id)

    logger.info(f"Получен запрос с query: '{query}'")
    try:
        # Запрашиваем количество страниц по запросу
        url = HHApiEndpoint.VACANCIES
        pages_response = await hh_client.get(
            url,
            params={"text": query, "per_page": 100},
        )
        logger.info(f"✅ HTTP ответ получен: статус {pages_response.status_code}")
        result = pages_response.json()
        pages = int(result["pages"])

        # Ограничиваем максимальное количество страниц
        if pages >= HH_MAX_PAGES:
            pages = HH_MAX_PAGES
            logger.info(f"Ограничено до {HH_MAX_PAGES} страниц")

        # Формируем параметры для всех страниц
        query_params = [{"text": query, "per_page": 100, "page": i} for i in range(pages)]

        # Выполняем запросы concurrently
        results = await fetch_data_gather(query_params, HH_CONCURRENT_REQUESTS, hh_client)

        # Собираем все вакансии в один список, отфильтровывая None
        vacancies_data = []
        for res in results:
            if res and "items" in res:
                vacancies_data.extend(res["items"])

        # Создаём директорию если нужно
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)

        # Сохраняем в файл
        async with aiofiles.open(output_path, "w", encoding="utf-8") as file:
            await file.write(json.dumps(vacancies_data, indent=2, ensure_ascii=False))

        logger.info(f"✅ Сохранено {len(vacancies_data)} вакансий в {output_path}")

        return {
            "vacancies_count": len(vacancies_data),
            "pages_processed": pages,
        }

    except httpx.HTTPStatusError as e:
        logger.error(f"❌ HTTP ошибка: {e.response.status_code}")
        raise HTTPException(
            status_code=e.response.status_code, detail=f"Ошибка API hh.ru: {e.response.status_code}"
        ) from None

    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке вакансий: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при загрузке вакансий: {e}") from None


async def filtered_vacancies(
    user_id: UUID,
    tiers: list[Experience] | None = None,
    input_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> dict[str, int]:
    """
    Читает вакансии из файла, фильтрует по уровню опыта и сохраняет результат.

    Args:
        user_id: ID пользователя
        tiers: Список уровней опыта для фильтрации (None = все уровни)
        input_path: Путь к входному файлу (по умолчанию из пользовательской директории)
        output_path: Путь к выходному файлу (по умолчанию из пользовательской директории)

    Returns:
        dict с количеством отфильтрованных вакансий
    """
    # Используем пользовательские пути по умолчанию
    if input_path is None or output_path is None:
        default_input, default_output = get_user_vacancy_files(user_id)
        input_path = input_path or default_input
        output_path = output_path or default_output

    try:
        # Если tiers не указан или пустой, выбираем все возможные уровни опыта
        if not tiers:
            tiers = list(Experience)
            logger.info(f"Tier не указан, используются все уровни опыта: {tiers}")
        else:
            logger.info(f"Фильтрация по уровням опыта: {tiers}")

        # Чтение входного файла
        async with aiofiles.open(input_path, encoding="utf-8") as file:
            content = await file.read()
            vacancies = json.loads(content)

        # Фильтрация вакансий
        result = []

        for vacancy in vacancies:
            experience = vacancy.get("experience")
            if experience and experience.get("id") in tiers:
                result.append(vacancy)

        logger.info(f"✅ Найдено {len(result)} вакансий из {len(vacancies)}")

        # Создаём директорию если нужно
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)

        # Создаём временный путь для атомарной записи
        temp_output_path = output_path_obj.with_suffix(f"{output_path_obj.suffix}.tmp")

        # Запись результата
        async with aiofiles.open(temp_output_path, mode="w", encoding="utf-8") as file:
            await file.write(json.dumps(result, indent=2, ensure_ascii=False))

        # Атомарно переименование на оригинальный название
        shutil.move(temp_output_path, output_path)

        logger.info(f"💾 Результат сохранён в: {output_path}")

        return {"filtered": len(result)}

    except FileNotFoundError:
        logger.error(f"❌ Файл не найден: {input_path}")
        raise HTTPException(
            status_code=404, detail="Файл с вакансиями не найден. Сначала выполните загрузку с hh.ru."
        ) from None

    except Exception as e:
        logger.error(f"❌ Ошибка при фильтрации вакансий: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при фильтрации вакансий: {e}") from None


async def import_vacancies(
    query: str,
    user_id: UUID,
    session: AsyncSession,
    tiers: list[Experience] | None = None,
) -> dict[str, int]:
    """
    Полный пайплайн импорта вакансий с hh.ru в базу данных.

    Последовательность:
    1. Загрузка вакансий с hh.ru → файл
    2. Фильтрация по уровню опыта → отдельный файл
    3. Сохранение отфильтрованных вакансий в БД

    Args:
        query: Поисковый запрос
        user_id: ID пользователя
        session: SQLAlchemy асинхронная сессия
        tiers: Список уровней опыта для фильтрации

    Returns:
        dict со статистикой выполнения:
            - fetched: сколько получено с hh.ru
            - filtered: сколько после фильтрации
            - total_found: всего найдено в файле
            - already_exists: уже было в БД
            - new_added: новых добавлено
            - errors: количество ошибок
    """
    logger.info(f"[Background] Начало импорта вакансий: query='{query}', user_id={user_id}")

    # Получаем клиент
    hh_client = await get_hh_client()

    try:
        fetch_result = await fetch_all_hh_vacancies(query, hh_client, user_id)
        logger.info("[Background] Шаг 1 завершён: вакансии загружены с hh.ru")

        # Шаг 2: Фильтрация
        filter_result = await filtered_vacancies(user_id, tiers)
        logger.info("[Background] Шаг 2 завершён: вакансии отфильтрованы")

        # Шаг 3: Сохранение в БД
        db_result = await vacancies_create(query, user_id, hh_client, session)
        logger.info("[Background] Шаг 3 завершён: вакансии сохранены в БД")

        logger.success(f"[Background] ✅ Импорт вакансий успешно завершён: query='{query}'")

        return {
            "fetched": fetch_result.get("vacancies_count", 0),
            "filtered": filter_result.get("filtered", 0),
            **db_result,
        }

    except HTTPException as e:
        logger.error(f"[Background] HTTP {e.status_code}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"[Background] ❌ Ошибка при импорте вакансий: {e}", exc_info=True)
        raise
