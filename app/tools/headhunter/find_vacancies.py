import asyncio
import json
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


BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
TEMP_DIR = BASE_DIR / "temp_files"

HH_API_URL = "https://api.hh.ru/vacancies"
HH_MAX_PAGES = 20  # Максимальное количество страниц для пагинации
HH_REQUEST_DELAY = 0.4  # Задержка между запросами в секундах (rate limiting)
HH_CONCURRENT_REQUESTS = 5  # Количество одновременных запросов

DEFAULT_VACANCIES_FILE = TEMP_DIR / "vacancies.json"
DEFAULT_FILTERED_VACANCIES_FILE = TEMP_DIR / "filtered_vacancies.json"


async def fetch_full_vacancy(vacancy_id: str, url: str = HH_API_URL) -> dict[str, Any]:
    """Получает полное описание вакансии"""
    async with httpx.AsyncClient() as client:
        try:
            # Создаём запрос к api hh.ru
            response = await client.get(f"{url}/{vacancy_id}", headers={"User-Agent": "parser_vacancies/0.1"})
            # Проверка статуса
            response.raise_for_status()

            # Десериализация
            full_vacancy = response.json()

            # Возвращаем ответ
            return cast(dict[str, Any], full_vacancy)

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP ошибка: {e.response.status_code}")
            raise HTTPException(status_code=e.response.status_code, detail="Вакансия не найдена") from None

        except Exception as e:
            logger.error(f"Ошибка при загрузке описании вакансии: {e}")
            raise HTTPException(status_code=500, detail=f"Ошибка при загрузке описании вакансии: {e}") from None


async def vacancies_create(
    query: str,
    user_id: UUID,
    session: AsyncSession,
    input_path: str | Path = DEFAULT_FILTERED_VACANCIES_FILE,
) -> None:
    """
    Пакетное добавление вакансий в бд
    """
    async with aiofiles.open(input_path, encoding="utf-8") as file:
        content = await file.read()
        vacancies = json.loads(content)

    all_ids = []

    for vac in vacancies:
        id_vac = vac.get("id")
        if id_vac:
            all_ids.append(vac["id"])

    stmt = select(Vacancy.hh_id).where(Vacancy.hh_id.in_(all_ids))
    result = await session.execute(stmt)
    existing_ids = {row.hh_id for row in result}

    new_ids = set(all_ids) - existing_ids

    logger.info(f"Всего найдено: {len(all_ids)}")
    logger.info(f"Уже в БД: {len(existing_ids)}")
    logger.info(f"Новых для загрузки: {len(new_ids)}")

    for hh_id in new_ids:
        try:
            details = await fetch_full_vacancy(hh_id)

            if not details:
                logger.warning(f"Не удалось получить данные для вакансии {hh_id}")
                continue

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

            vacancy = Vacancy(
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

            session.add(vacancy)
            await asyncio.sleep(HH_REQUEST_DELAY)

        except Exception as e:
            logger.error(f"Ошибка при обработке вакансии {hh_id}: {e}")
            continue

    await session.commit()
    logger.info("Загрузка вакансий в бд завершено")


async def fetch_with_semaphore(
    semaphore: asyncio.Semaphore, client: httpx.AsyncClient, url: str, param: dict[str, Any]
) -> dict[str, Any] | None:
    """Выделяем канал для запроса"""
    async with semaphore:
        try:
            response = await client.get(url, params=param)
            if response.status_code != 200:
                logger.warning(f"Запрос упал с ошибкой: статус {response.status_code}")
                return None
            logger.info(f"Успешный запрос: страница {param.get('page', 'N/A')}")
            return cast(dict[str, Any], response.json())
        except Exception as e:
            logger.error(f"Ошибка при выполнении запроса {param}: {e}")
            return None


async def fetch_data_gather(param: list, connect: int) -> list[Any]:
    """Объединяем запросы в пул"""
    semaphore = asyncio.Semaphore(connect)
    async with httpx.AsyncClient() as client:
        tasks = [fetch_with_semaphore(semaphore, client, url=url, param=data) for data, url in param]
        result = await asyncio.gather(*tasks)
        return cast(list[Any], result)


async def fetch_all_hh_vacancies(
    query: str, url: str = HH_API_URL, input_path: str | Path = DEFAULT_VACANCIES_FILE
) -> dict[str, Any]:
    """
    Загружаем асинхронно несколько страниц и сохраняем в файл
    запрос -> django OR fastapi OR aiohttp OR litestar OR flask
    """
    logger.info(f"Получен запрос с query: '{query}'")
    try:
        # Запрашиваем кол-во страниц по запросу
        async with httpx.AsyncClient() as client:
            pages_response = await client.get(url, params={"text": query, "per_page": 100})
            result = pages_response.json()
            pages = int(result["pages"])
            logger.info(f"По запросу '{query}' найдено страниц: {pages}")
        # Ограничиваем максимальное количество страниц
        if pages >= HH_MAX_PAGES:
            pages = HH_MAX_PAGES

        vacancies_data = []

        # Формируем параметры для всех страниц
        query_params = [({"text": query, "per_page": 100, "page": i}, url) for i in range(pages)]

        # Выполняем запросы concurrently
        results = await fetch_data_gather(query_params, HH_CONCURRENT_REQUESTS)

        # Собираем все вакансии в один список, отфильтровывая None
        for res in results:
            if res and "items" in res:
                vacancies_data.extend(res["items"])

        logger.info(f"Всего получено вакансий: {len(vacancies_data)}")

        # Сохраняем в файл с указанием кодировки UTF-8
        async with aiofiles.open(input_path, "w", encoding="utf-8") as file:
            await file.write(json.dumps(vacancies_data, indent=2, ensure_ascii=False))

        logger.info(f"Данные сохранены в файл: {input_path}")

        return {"vacancies_count": len(vacancies_data), "pages_processed": pages}

    except Exception as e:
        logger.error(f"Ошибка при загрузке вакансий: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка при загрузке вакансий: {e}") from None


async def filtered_vacancies(
    tiers: list[Experience] | None,
    input_path: str | Path = DEFAULT_VACANCIES_FILE,
    output_path: str | Path = DEFAULT_FILTERED_VACANCIES_FILE,
) -> dict[str, int]:
    """
    Читает вакансии, фильтрует по tiers и сохраняет результат
    """

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
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Запись результата
        async with aiofiles.open(output_path, mode="w", encoding="utf-8") as file:
            await file.write(json.dumps(result, indent=2, ensure_ascii=False))

        logger.info(f"💾 Результат сохранён в: {output_path}")

        return {"Найдено": len(result)}

    except Exception as e:
        logger.error(f"Ошибка при загрузке вакансий: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка при загрузке вакансий: {e}") from None


async def import_vacancies(
    query: str,
    tiers: list[Experience] | None,
    user_id: UUID,
    session: AsyncSession,
) -> None:
    """
    Полный пайплайн импорта вакансий с hh.ru в базу данных.

    Запускается как background task, поэтому ничего не возвращает.
    Результаты выполнения отслеживаются через логирование.
    """
    logger.info(f"[Background] Начало импорта вакансий: query='{query}', user_id={user_id}")
    try:
        await fetch_all_hh_vacancies(query)
        logger.info("[Background] Шаг 1 завершён: вакансии загружены с hh.ru")
        await filtered_vacancies(tiers)
        logger.info("[Background] Шаг 2 завершён: вакансии отфильтрованы")
        await vacancies_create(query, user_id, session)
        logger.info("[Background] Шаг 3 завершён: вакансии сохранены в БД")

        logger.success(f"[Background] ✅ Импорт вакансий успешно завершён: query='{query}'")
    except HTTPException as e:
        logger.error(f"[Background] HTTP {e.status_code}: {str(e)}")
    except Exception as e:
        logger.error(f"[Background] ❌ Ошибка при импорте вакансий: {e}", exc_info=True)
