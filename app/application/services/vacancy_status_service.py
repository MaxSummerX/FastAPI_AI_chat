"""
Синхронизация архивных статусов вакансий с hh.ru.

Проверяет статус вакансий (archived=True/False) через API hh.ru и обновляет БД.
Персистентность — через IVacancyRepository, HTTP — infrastructure/hh.
"""

import asyncio

import httpx
from loguru import logger

from app.domain.repositories.vacancies import IVacancyRepository
from app.infrastructure.hh.exceptions import RateLimitError
from app.infrastructure.hh.headhunter_client import HHApiEndpoint


SEMAPHORE_COUNT = 3
REQUEST_DELAY = 2


class VacancyArchiveSync:
    """
    Сервис синхронизации архивного статуса вакансий с hh.ru.

    Использует семафор для ограничения параллельных запросов и
    retry с экспоненциальной задержкой при 429.

    Attributes:
        vacancy_repo: Репозиторий вакансий
        hh_client: HTTP клиент для запросов к hh.ru
        semaphore: Семафор для ограничения параллельных запросов
        request_delay: Задержка между запросами в секундах
    """

    def __init__(
        self,
        vacancy_repo: IVacancyRepository,
        hh_client: httpx.AsyncClient,
        semaphore_count: int = SEMAPHORE_COUNT,
        request_delay: float = REQUEST_DELAY,
    ) -> None:
        self.vacancy_repo = vacancy_repo
        self.hh_client = hh_client
        self.semaphore = asyncio.Semaphore(semaphore_count)
        self.request_delay = request_delay

    async def _fetch_vacancy_status(self, hh_id: str) -> bool | None:
        """
        Получает статус архивации вакансии из hh.ru API.

        Returns:
            True если вакансия архивирована или скрыта (404)
            False если вакансия активна
            None если произошла ошибка (кроме 404)

        Raises:
            RateLimitError: При получении 429 от API
        """
        async with self.semaphore:
            try:
                url = HHApiEndpoint.VACANCIES_BY_ID.format(vacancy_id=hh_id)
                response = await self.hh_client.get(url)

                if response.status_code == 429:
                    raise RateLimitError(f"Rate limit для {hh_id}")

                # если вакансия скрыта работодателем, при попытке запроса она возвращает 404
                if response.status_code == 404:
                    logger.warning("Вакансия была скрыта работодателем: {}", hh_id)
                    return True

                if response.status_code != 200:
                    logger.warning("Неожиданный статус {} для {}", response.status_code, hh_id)
                    return None

                json_data = response.json()
                return bool(json_data.get("archived", False))

            except RateLimitError:
                raise

            except Exception as e:
                logger.error("⚠️ Произошла ошибка при запросе {}: {}", hh_id, e)
                return None

            finally:
                await asyncio.sleep(self.request_delay)

    async def _fetch_with_retry(self, hh_id: str) -> bool | None:
        """
        Получает статус вакансии с экспоненциальным retry при 429.

        Делает до 3 попыток с экспоненциальной задержкой (2, 4, 8 сек).
        """
        for attempt in range(1, 4):
            try:
                return await self._fetch_vacancy_status(hh_id)
            except RateLimitError:
                wait = 2**attempt
                logger.warning("429 retry {}/3 для {}, ждём {} сек", attempt, hh_id, wait)
                await asyncio.sleep(wait)

        logger.error("Rate limit исчерпан для {}", hh_id)
        return None

    async def _fetch_all_statuses(self, hh_ids: list[str]) -> list[bool | None]:
        """
        Пакетное получение статусов вакансий через asyncio.gather.

        Returns:
            Список статусов в том же порядке, что и hh_ids.
            True - архивирована, False - активна, None - ошибка.
        """
        tasks = [self._fetch_with_retry(hh_id) for hh_id in hh_ids]
        results = await asyncio.gather(*tasks)
        return list(results)

    async def sync_archive_statuses(self) -> dict:
        """
        Основной метод синхронизации архивных статусов вакансий.

        Выполняет полный пайплайн:
        1. Получает активные вакансии из БД
        2. Проверяет их статус через hh.ru API
        3. Обновляет БД с полученными данными

        Returns:
            Словарь со статистикой выполнения:
            - processed: количество успешно обработанных вакансий
            - skipped: количество пропущенных (ошибки API)
            - total: общее количество проверенных вакансий
        """
        logger.info("Запуск синхронизации статусов вакансий")
        start_time = asyncio.get_running_loop().time()

        hh_ids = sorted(await self.vacancy_repo.get_active_hh_ids())
        if not hh_ids:
            logger.info("Нет активных вакансий для синхронизации")
            return {"processed": 0, "skipped": 0, "total": 0}

        logger.info("Найдено активных вакансий в БД: {}", len(hh_ids))

        values = await self._fetch_all_statuses(hh_ids)

        total = len(hh_ids)
        data = {hh_id: value for hh_id, value in zip(hh_ids, values, strict=True) if value is not None}
        processed = len(data)
        skipped = total - processed

        if data:
            await self.vacancy_repo.update_archive_statuses(data)

        elapsed = asyncio.get_event_loop().time() - start_time
        logger.info("Обработано: {}/{}, пропущено: {}, время: {:.2f} сек", processed, total, skipped, elapsed)

        return {"processed": processed, "skipped": skipped, "total": total}
