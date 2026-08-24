"""
Импорт вакансий с hh.ru в базу данных.

Пайплайн: загрузка страниц поиска с hh.ru -> фильтрация по опыту -> сохранение в БД.
Персистентность вынесена в IVacancyRepository, HTTP — в infrastructure/hh.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import aiofiles
import httpx
from fastapi import HTTPException
from loguru import logger
from sqlalchemy.exc import IntegrityError

from app.domain.enums.experience import Experience
from app.domain.models.user_vacancies import UserVacancies
from app.domain.models.vacancy import Vacancy
from app.domain.repositories.vacancies import IVacancyRepository
from app.infrastructure.hh.headhunter_client import (
    HH_MAX_PAGES,
    get_hh_client,
)
from app.infrastructure.hh.hh_web_parser import (
    fetch_search_page,
    fetch_vacancy_details,
    pages_for_total,
    polite_sleep,
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
    Получает полное описание вакансии по ID (Scraping страницы hh.ru/vacancy/{id}).

    Raises:
        HTTPException: если вакансия не найдена или произошла ошибка
    """
    try:
        details = await fetch_vacancy_details(hh_client, vacancy_id)
        if details is None:
            raise HTTPException(status_code=404, detail="Вакансия не найдена")
        return details

    except HTTPException:
        raise

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
    if isinstance(published_at_str, str):
        try:
            published_at = datetime.fromisoformat(published_at_str)
        except ValueError as e:
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

    @staticmethod
    async def _fetch_all_hh_vacancies(
        query: str,
        hh_client: httpx.AsyncClient,
        user_id: UUID,
        output_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """
        Загружает страницы поиска с вакансиями и сохраняет в файл.

        Scraping: страницы проходятся последовательно с паузой и джиттером
        (параллельные запросы к HTML-страницам быстро ловят анти-бот hh.ru).
        """
        if output_path is None:
            output_path, _ = get_user_vacancy_files(user_id)

        logger.info(f"Получен запрос с query: '{query}'")
        try:
            vacancies_data: list[dict[str, Any]] = []
            pages = 0

            for page in range(HH_MAX_PAGES):
                items, total = await fetch_search_page(hh_client, query, page)
                if page == 0:
                    pages = pages_for_total(total, HH_MAX_PAGES)
                    logger.info(f"Найдено {total} вакансий, страниц к обходу: {pages}")

                logger.info(f"✅ Страница {page}: {len(items)} вакансий")
                vacancies_data.extend(items)

                page += 1
                if page >= pages or not items:
                    break
                await polite_sleep()

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
                status_code=e.response.status_code, detail=f"Ошибка hh.ru: {e.response.status_code}"
            ) from None

        except Exception as e:
            logger.error(f"❌ Ошибка при загрузке вакансий: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Ошибка при загрузке вакансий: {e}") from None

    @staticmethod
    async def _filtered_vacancies(
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

        vacancies_to_add: list[Vacancy] = []
        error_count = 0
        total_new = len(new_vacancies)
        saved_count = 0
        chunk_size = 10

        # Связи для существующих вакансий (для новых репозиторий создаст сам после flush)
        links_to_add = [UserVacancies(user_id=user_id, vacancy_id=existing_vacancies[hh_id]) for hh_id in new_links]

        async def save_chunk() -> None:
            """Коммитит накопленный chunk: обрыв задачи теряет только последний chunk."""
            nonlocal vacancies_to_add, saved_count, error_count
            if not vacancies_to_add and not links_to_add:
                return

            chunk, vacancies_to_add = vacancies_to_add, []

            try:
                await self.vacancy_repo.bulk_save_with_links(chunk, links_to_add, user_id)
                saved_count += len(chunk)
            except IntegrityError:
                logger.warning("Конфликт уникальности в chunks, переходим на поштучную вставку")
                await self.vacancy_repo.rollback()

                for vac in chunk:
                    try:
                        await self.vacancy_repo.bulk_save_with_links([vac], [], user_id)
                        saved_count += 1
                    except IntegrityError:
                        # вакансию успела вставить параллельная задача — только связываем
                        await self.vacancy_repo.rollback()
                        existing = await self.vacancy_repo.get_by_hh_id(vac.hh_id)
                        if existing is not None:
                            if not await self.vacancy_repo.has_user_link(user_id, existing.id):
                                await self.vacancy_repo.create_link(user_id, existing.id)
                        else:
                            error_count += 1
                            logger.error(f"Вакансия {vac.hh_id} конфликтует, но не найдена в БД")

            links_to_add.clear()  # связи существующих пишутся только с первым chunk
            logger.info(f"💾 Chunk закоммичен: всего сохранено в БД {saved_count} (ошибок: {error_count})")

        for processed, hh_id in enumerate(new_vacancies, start=1):
            try:
                vacancies_to_add.append(await create_vacancy_object(hh_id, query, hh_client))
                await polite_sleep()  # Человекоподобная пауза
                if len(vacancies_to_add) >= chunk_size:
                    await save_chunk()
            except Exception as e:
                logger.error(f"Ошибка при обработке вакансии {hh_id}: {e}")
                error_count += 1
                continue
            finally:
                # Каждый запрос деталей ~3-4с, без прогресс-лога цикл выглядит как зависание
                if processed % 25 == 0 or processed == total_new:
                    logger.info(f"Детали вакансий: {processed}/{total_new} (ошибок: {error_count})")

        await save_chunk()

        logger.info("Загрузка вакансий в БД завершена")

        return {
            "total_found": len(all_ids),
            "already_linked": len(linked_ids),
            "new_vacancies": saved_count,
            "new_links": len(new_links),
            "errors": error_count,
        }
