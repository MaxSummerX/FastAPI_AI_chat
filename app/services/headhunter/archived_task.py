import asyncio

import httpx
from loguru import logger
from sqlalchemy import case, select, update

from app.database.postgres_db import async_session_maker
from app.models.vacancies import Vacancy as VacancyModel
from app.services.headhunter.find_vacancies import fetch_full_vacancy
from app.services.headhunter.headhunter_client import HHApiEndpoint, get_hh_client


# TODO: 1. Клиенты и сессии для работы парсера должны поступать как зависимость
# TODO: 2. Продумать rate limit + timeout
# TODO: 3. Добавить обработку ошибок и логирование
# 404 -> у вакансий есть 3 состояния, есть скрытая вакансия при попытке запроса она возвращает 404
# Завернуть всё в класс сервис?


async def archive_from_db(num: int) -> None:
    """Функция заготовка для проверки работы парсинга архивного состояния вакансии со сменой статуса в бд"""
    hh_ids = []
    # Создаем сессию для подключения к дб
    async with async_session_maker() as session:
        # Делаем запрос на все hh_id, где вакансии имеют статус не в архиве (False)
        result_from_db = await session.scalars(select(VacancyModel.hh_id).where(VacancyModel.is_archived.is_(False)))

        # Сохраняем все ключи hh_id
        values = result_from_db.all()

    # Создаем клиента для подключения к HH.ru
    async with await get_hh_client() as client:
        # Делаем разовый запрос для получения данных по hh_id
        result_from_hh = await fetch_full_vacancy(values[num], client)
    # Выделяем поля отвечающие за то что находится ли вакансия в архиве
    arch = result_from_hh.get("archived", False)

    # Если вакансия на HH.ru архиве, то меняем в нашей бд статус данных консистентно на HH.ru (True вакансия в архиве)
    if arch:
        hh_ids.append(values[num])
        # Создаем сессию для подключения к дб
        async with async_session_maker() as session:
            # Передаем значения для обновления поля в таблице по hh_id в бд
            await session.execute(update(VacancyModel).where(VacancyModel.hh_id.in_(hh_ids)).values(is_archived=arch))
            logger.info("Вакансия c hh_id: {} меняет статус на {} и теперь находится в архиве", values[num], arch)
            # Делаем коммит в бд, чтобы сохранить результат
            await session.commit()


async def fetch_with_semaphore(hh_id: str, semaphore: asyncio.Semaphore, client: httpx.AsyncClient) -> bool:
    """Запрос через семафор"""
    async with semaphore:
        try:
            url = HHApiEndpoint.VACANCIES_BY_ID.format(vacancy_id=hh_id)
            response = await client.get(url)
            if response.status_code == 404:
                logger.warning(f"Вакансия была скрыта работодателем {response.status_code} -> {url}")
                return False

            if response.status_code != 200:
                logger.warning(f"Запрос упал с ошибкой: статус {response.status_code}")
                return False  # Исправить, добавить обработку

            json_data = response.json()
            return json_data.get("archived", False)  # type: ignore

        except Exception as e:
            logger.error(f"⚠️ Произошла ошибка при запросе: {e}")
            raise


async def fetch_data_gather(max_connections: int, hh_client: httpx.AsyncClient, ids: list) -> list[bool]:
    """Gather с ограничением через семафор"""
    semaphore = asyncio.Semaphore(max_connections)
    tasks = [fetch_with_semaphore(id_hh, semaphore, hh_client) for id_hh in ids]
    return await asyncio.gather(*tasks)


async def ids_from_db() -> list[str]:
    """Получаем все id_hh из бд"""
    async with async_session_maker() as session:
        # Делаем запрос на все hh_id, где вакансии имеют статус не в архиве (False)
        result_from_db = await session.scalars(select(VacancyModel.hh_id).where(VacancyModel.is_archived.is_(False)))
        # Сохраняем все ключи hh_id
        values = result_from_db.all()
    return list(values)


async def fetch_in_batches(hh_ids: list[str], batch_size: int, client: httpx.AsyncClient) -> list[bool]:
    """Пакетные запросы через fetch_data_gather"""
    results = []
    for num in range(0, len(hh_ids), batch_size):
        ids = hh_ids[num : num + batch_size]
        data = await fetch_data_gather(5, client, ids)
        results.extend(data)
    return results


async def sava_status_ids(hh_ids: dict[str, bool]) -> None:
    """Пакетное сохранение в бд"""
    async with async_session_maker() as session:
        await session.execute(
            update(VacancyModel)
            .where(VacancyModel.hh_id.in_(hh_ids.keys()))
            .values(
                is_archived=case(
                    *[(VacancyModel.hh_id == hh_id, value) for hh_id, value in hh_ids.items()],
                    else_=VacancyModel.is_archived,
                )
            )
        )
        await session.commit()


async def main() -> None:
    """Тестовая реализация пайплайна"""
    res = await ids_from_db()
    hh_ids = res[:10]

    async with await get_hh_client() as client:
        values = await fetch_in_batches(hh_ids, 5, client)

    data = dict(zip(hh_ids, values, strict=True))
    await sava_status_ids(data)


asyncio.run(main())
