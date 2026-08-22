"""
Импорт вакансий с hh.ru в базу данных.

Пайплайн: загрузка страниц поиска с hh.ru -> фильтрация по опыту -> сохранение в БД.
Персистентность вынесена в IVacancyRepository, HTTP — в infrastructure/hh.
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

from app.domain.enums.experience import Experience
from app.domain.models.user_vacancies import UserVacancies
from app.domain.models.vacancy import Vacancy
from app.domain.repositories.vacancies import IVacancyRepository
from app.infrastructure.hh.headhunter_client import (
    HH_CONCURRENT_REQUESTS,
    HH_MAX_PAGES,
    HH_REQUEST_DELAY,
    HHApiEndpoint,
    get_hh_client,
)


BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
TEMP_DIR = BASE_DIR / "temp_files" / "hh"


def get_user_vacancy_files(user_id: UUID) -> tuple[Path, Path]:
    """
    Возвращает пути к файлам вакансий для конкретного пользователя.

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

    Raises:
        HTTPException: если вакансия не найдена или произошла ошибка
    """
    try:
        url = HHApiEndpoint.VACANCIES_BY_ID.format(vacancy_id=vacancy_id)
        response = await hh_client.get(url)
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP ошибка: {e.response.status_code}")
        raise HTTPException(status_code=e.response.status_code, detail="Вакансия не найдена") from None

    except Exception as e:
        logger.error(f"Ошибка при загрузке вакансии {vacancy_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка при загрузке описании вакансии: {e}") from None


async def create_vacancy_object(hh_id: str, query: str, hh_client: httpx.AsyncClient) -> Vacancy:
    """
    Создаёт объект Vacancy на основе данных с hh.ru (без сохранения в БД).
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
            published_at = datetime.fromisoformat(published_at_str)
        except (ValueError, TypeError) as e:
            logger.warning(f"Не удалось распарсить дату {published_at_str}: {e}")

    return Vacancy(
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


async def _fetch_with_semaphore(
    semaphore: asyncio.Semaphore, client: httpx.AsyncClient, params: dict[str, Any]
) -> dict[str, Any] | None:
    """Выполняет запрос с ограничением по количеству одновременных соединений."""
    async with semaphore:
        try:
            response = await client.get(HHApiEndpoint.VACANCIES, params=params)
            if response.status_code != 200:
                logger.warning(f"Запрос упал с ошибкой: статус {response.status_code}")
                return None
            logger.info(f"Успешный запрос: страница {params.get('page', 'N/A')}")
            return cast(dict[str, Any], response.json())
        except Exception as e:
            logger.error(f"Ошибка при выполнении запроса {params}: {e}")
            return None


class VacancyImportService:
    """
    Полный пайплайн импорта вакансий с hh.ru:

    1. Загрузка страниц поиска -> файл
    2. Фильтрация по уровню опыта -> файл
    3. Сохранение в БД (новые вакансии + связи user<->vacancy)
    """

    def __init__(self, vacancy_repo: IVacancyRepository) -> None:
        self.vacancy_repo = vacancy_repo

    async def import_vacancies(
        self,
        query: str,
        user_id: UUID,
        tiers: list[Experience] | None = None,
    ) -> dict[str, int]:
        """
        Полный пайплайн импорта вакансий с hh.ru в базу данных.

        Returns:
            dict со статистикой: fetched / filtered / total_found /
            already_linked / new_vacancies / new_links / errors
        """
        logger.info(f"[Background] Начало импорта вакансий: query='{query}', user_id={user_id}")

        hh_client = await get_hh_client()

        try:
            fetch_result = await self._fetch_all_hh_vacancies(query, hh_client, user_id)
            logger.info("[Background] Шаг 1 завершён: вакансии загружены с hh.ru")

            filter_result = await self._filtered_vacancies(user_id, tiers)
            logger.info("[Background] Шаг 2 завершён: вакансии отфильтрованы")

            db_result = await self._vacancies_create(query, user_id, hh_client)
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

    async def _fetch_all_hh_vacancies(
        self,
        query: str,
        hh_client: httpx.AsyncClient,
        user_id: UUID,
        output_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Загружает асинхронно несколько страниц с вакансиями и сохраняет в файл."""
        if output_path is None:
            output_path, _ = get_user_vacancy_files(user_id)

        logger.info(f"Получен запрос с query: '{query}'")
        try:
            pages_response = await hh_client.get(
                HHApiEndpoint.VACANCIES,
                params={"text": query, "per_page": 100},
            )
            logger.info(f"✅ HTTP ответ получен: статус {pages_response.status_code}")
            result = pages_response.json()
            pages = int(result["pages"])

            if pages >= HH_MAX_PAGES:
                pages = HH_MAX_PAGES
                logger.info(f"Ограничено до {HH_MAX_PAGES} страниц")

            query_params = [{"text": query, "per_page": 100, "page": i} for i in range(pages)]

            semaphore = asyncio.Semaphore(HH_CONCURRENT_REQUESTS)
            tasks = [_fetch_with_semaphore(semaphore, hh_client, param) for param in query_params]
            results = await asyncio.gather(*tasks)

            vacancies_data = []
            for res in results:
                if res and "items" in res:
                    vacancies_data.extend(res["items"])

            output_path_obj = Path(output_path)
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)

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

    async def _filtered_vacancies(
        self,
        user_id: UUID,
        tiers: list[Experience] | None = None,
        input_path: str | Path | None = None,
        output_path: str | Path | None = None,
    ) -> dict[str, int]:
        """Читает вакансии из файла, фильтрует по уровню опыта и сохраняет результат."""
        if input_path is None or output_path is None:
            default_input, default_output = get_user_vacancy_files(user_id)
            input_path = input_path or default_input
            output_path = output_path or default_output

        try:
            if not tiers:
                tiers = list(Experience)
                logger.info(f"Tier не указан, используются все уровни опыта: {tiers}")
            else:
                logger.info(f"Фильтрация по уровням опыта: {tiers}")

            async with aiofiles.open(input_path, encoding="utf-8") as file:
                content = await file.read()
                vacancies = json.loads(content)

            result = []
            for vacancy in vacancies:
                experience = vacancy.get("experience")
                if experience and experience.get("id") in tiers:
                    result.append(vacancy)

            logger.info(f"✅ Найдено {len(result)} вакансий из {len(vacancies)}")

            output_path_obj = Path(output_path)
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)

            temp_output_path = output_path_obj.with_suffix(f"{output_path_obj.suffix}.tmp")

            async with aiofiles.open(temp_output_path, mode="w", encoding="utf-8") as file:
                await file.write(json.dumps(result, indent=2, ensure_ascii=False))

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

    async def _vacancies_create(
        self,
        query: str,
        user_id: UUID,
        hh_client: httpx.AsyncClient,
    ) -> dict[str, int]:
        """
        Сохраняет вакансии из файла в БД через репозиторий.

        Дедупликация: новые вакансии создаются, для существующих —
        только связи user<->vacancy.
        """
        _, input_path = get_user_vacancy_files(user_id)

        async with aiofiles.open(input_path, encoding="utf-8") as file:
            content = await file.read()
            vacancies = json.loads(content)

        all_ids = [vac.get("id") for vac in vacancies if vac.get("id")]

        existing_vacancies = await self.vacancy_repo.get_existing_hh_id_map(all_ids)
        linked_ids = await self.vacancy_repo.get_user_linked_hh_ids(user_id, all_ids)

        new_vacancies = set(all_ids) - existing_vacancies.keys()
        new_links = existing_vacancies.keys() - linked_ids

        logger.info(f"Всего найдено: {len(all_ids)}")
        logger.info(f"Уже у пользователя: {len(linked_ids)}")
        logger.info(f"Новых вакансий: {len(new_vacancies)}")
        logger.info(f"Новых связей: {len(new_links)}")

        vacancies_to_add = []
        error_count = 0

        for hh_id in new_vacancies:
            try:
                vacancies_to_add.append(await create_vacancy_object(hh_id, query, hh_client))
                await asyncio.sleep(HH_REQUEST_DELAY)
            except Exception as e:
                logger.error(f"Ошибка при обработке вакансии {hh_id}: {e}")
                error_count += 1
                continue

        # Связи для существующих вакансий (для новых репозиторий создаст сам после flush)
        links_to_add = [UserVacancies(user_id=user_id, vacancy_id=existing_vacancies[hh_id]) for hh_id in new_links]

        await self.vacancy_repo.bulk_save_with_links(vacancies_to_add, links_to_add, user_id)

        logger.info("Загрузка вакансий в БД завершена")

        return {
            "total_found": len(all_ids),
            "already_linked": len(linked_ids),
            "new_vacancies": len(vacancies_to_add),
            "new_links": len(new_links),
            "errors": error_count,
        }
