import asyncio

from loguru import logger
from sqlalchemy import select, update

from app.database.postgres_db import async_session_maker
from app.models.vacancies import Vacancy as VacancyModel
from app.services.headhunter.find_vacancies import fetch_full_vacancy
from app.services.headhunter.headhunter_client import get_hh_client


# TODO: 1. Клиенты и сессии для работы парсера должны поступать как зависимость
# TODO: 2. Нужно продумать множественные асинхронные запросы с использованием семафора + rate limit + timeout
# TODO: 3. Продумать как лучше сохранять результат парсинга в бд, делать вызов после каждого запроса или делать 1 общий


async def archive_from_db(num: int) -> None:
    """Функция заготовка для проверки работы парсинга архивного состояния вакансии со сменой статуса в бд"""

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
    # Выделяем поля отвечающее за то что находится ли вакансия в архиве
    arch = result_from_hh.get("archived", False)

    # Если вакансия на HH.ru архиве, то меняем в нашей бд статус консистентно данных на HH.ru (True вакансия в архиве)
    if arch:
        # Создаем сессию для подключения к дб
        async with async_session_maker() as session:
            # Передаем значения для обновления поля в таблице по hh_id в бд
            await session.execute(
                update(VacancyModel).where(VacancyModel.hh_id == values[num]).values(is_archived=arch)
            )
            logger.info("Вакансия c hh_id: {} меняет статус на {} и теперь находиться в архиве", values[num], arch)
            # Делаем коммит в бд, чтобы сохранить результат
            await session.commit()


asyncio.run(archive_from_db(-1))
