import asyncio

import httpx
from loguru import logger
from sqlalchemy import case, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vacancies import Vacancy as VacancyModel
from app.services.headhunter.exceptions import RateLimitError
from app.services.headhunter.headhunter_client import HHApiEndpoint


SEMAPHORE_COUNT = 3
REQUEST_DELAY = 2


class VacancyArchiveSync:
    """
    Сервис для синхронизации архивного статуса вакансий с hh.ru.

    Проверяет статус вакансий (archived=True/False) через API hh.ru и обновляет БД.
    Использует семафор для ограничения параллельных запросов и retry при 429.

    Attributes:
        db: Сессия асинхронной БД
        hh_client: HTTP клиент для запросов к hh.ru
        semaphore: Семафор для ограничения параллельных запросов
        request_delay: Задержка между запросами в секундах
    """

    def __init__(
        self,
        db_session: AsyncSession,
        hh_client: httpx.AsyncClient,
        semaphore_count: int = SEMAPHORE_COUNT,
        request_delay: float = REQUEST_DELAY,
    ) -> None:
        """
        Инициализация сервиса синхронизации.

        Args:
            db_session: Асинхронная сессия БД
            hh_client: HTTP клиент для запросов к hh.ru API
            semaphore_count: Максимальное количество параллельных запросов (по умолчанию 3)
            request_delay: Задержка между запросами в секундах (по умолчанию 2)
        """
        self.db = db_session
        self.hh_client = hh_client
        self.semaphore = asyncio.Semaphore(semaphore_count)
        self.request_delay = request_delay

    async def _fetch_vacancy_status(self, hh_id: str) -> bool | None:
        """
        Получает статус архивации вакансии из hh.ru API.

        Args:
            hh_id: Идентификатор вакансии на hh.ru

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

        Args:
            hh_id: Идентификатор вакансии на hh.ru

        Returns:
            True если вакансия архивирована, False если активна, None при ошибке
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

    async def _fetch_all_statuses(
        self,
        hh_ids: list[str],
    ) -> list[bool | None]:
        """
        Пакетное получение статусов вакансий через asyncio.gather.

        Args:
            hh_ids: Список идентификаторов вакансий на hh.ru

        Returns:
            Список статусов вакансий в том же порядке, что и hh_ids.
            True - архивирована, False - активна, None - ошибка.
        """
        tasks = [self._fetch_with_retry(hh_id) for hh_id in hh_ids]
        results = await asyncio.gather(*tasks)
        return list(results)

    async def _get_active_vacancy_ids(self) -> list[str]:
        """
        Получает идентификаторы всех активных (неархивных) вакансий из БД.

        Returns:
            Список hh_id вакансий, у которых is_archived=False

        Raises:
            Exception: При ошибке запроса к БД
        """
        try:
            result_from_db = await self.db.scalars(
                select(VacancyModel.hh_id).where(VacancyModel.is_archived.is_(False))
            )
            values = result_from_db.all()
            return list(values)
        except Exception as e:
            logger.error("Ошибка при получении вакансий из БД: {}", e)
            raise

    async def _update_archive_statuses(self, hh_ids: dict[str, bool]) -> None:
        """
        Пакетное обновление архивных статусов вакансий в БД.

        Args:
            hh_ids: Словарь {hh_id: archived_status} для обновления

        Raises:
            Exception: При ошибке обновления БД (с rollback)
        """
        try:
            await self.db.execute(
                update(VacancyModel)
                .where(VacancyModel.hh_id.in_(hh_ids.keys()))
                .values(
                    is_archived=case(
                        *[(VacancyModel.hh_id == hh_id, value) for hh_id, value in hh_ids.items()],
                        else_=VacancyModel.is_archived,
                    )
                )
            )
            await self.db.commit()
            logger.info("БД обновлена: {} записей", len(hh_ids))
        except Exception as e:
            await self.db.rollback()
            logger.error("Ошибка при обновлении статусов в БД: {}", e)
            raise

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

        hh_ids = await self._get_active_vacancy_ids()
        if not hh_ids:
            logger.info("Нет активных вакансий для синхронизации")
            return {"processed": 0, "skipped": 0, "total": 0}

        logger.info("Найдено активных вакансий в БД: {}", len(hh_ids))

        values = await self._fetch_all_statuses(hh_ids)

        total = len(hh_ids)
        data = {hh_id: value for hh_id, value in zip(hh_ids, values, strict=True) if value is not None}
        processed = len(data)
        skipped = total - processed

        await self._update_archive_statuses(data)

        elapsed = asyncio.get_event_loop().time() - start_time
        logger.info("Обработано: {}/{}, пропущено: {}, время: {:.2f} сек", processed, total, skipped, elapsed)

        return {"processed": processed, "skipped": skipped, "total": total}
