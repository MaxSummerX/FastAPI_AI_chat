import asyncio
import json
from pathlib import Path
from typing import Any, cast

import aiofiles
import httpx
from fastapi import HTTPException
from loguru import logger


BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent


HH_API_URL = "https://api.hh.ru/vacancies"


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

            # Определяем куда сохранить json файл
            output_path = BASE_DIR / "vacancy.json"

            # Асинхронно сохраняем вакансию
            async with aiofiles.open(output_path, "w", encoding="utf-8") as file:
                await file.write(json.dumps(full_vacancy, ensure_ascii=False, indent=2))

            # Возвращаем ответ
            return cast(dict[str, Any], full_vacancy)

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP ошибка: {e.response.status_code}")
            raise HTTPException(status_code=e.response.status_code, detail="Вакансия не найдена") from None

        except Exception as e:
            logger.error(f"Ошибка при загрузке описании вакансии: {e}")
            raise HTTPException(status_code=500, detail=f"Ошибка при загрузке описании вакансии: {e}") from None


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


async def fetch_all_hh_vacancies(query: str, url: str = HH_API_URL) -> dict[str, Any]:
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
        if pages >= 20:
            pages = 20

        vacancies_data = []

        # Формируем параметры для всех страниц
        query_params = [({"text": query, "per_page": 100, "page": i}, url) for i in range(pages)]

        # Выполняем запросы concurrently
        results = await fetch_data_gather(query_params, 5)

        # Собираем все вакансии в один список, отфильтровывая None
        for res in results:
            if res and "items" in res:
                vacancies_data.extend(res["items"])

        logger.info(f"Всего получено вакансий: {len(vacancies_data)}")

        # Сохраняем в файл с указанием кодировки UTF-8
        output_path = BASE_DIR / "vacancies.json"
        async with aiofiles.open(output_path, "w", encoding="utf-8") as file:
            await file.write(json.dumps(vacancies_data, indent=2, ensure_ascii=False))

        logger.info(f"Данные сохранены в файл: {output_path}")

        return {"answer": "in progress", "vacancies_count": len(vacancies_data), "pages_processed": pages}

    except Exception as e:
        logger.error(f"Ошибка при загрузке вакансий: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка при загрузке вакансий: {e}") from None
