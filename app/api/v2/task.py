import os
from typing import Any

import redis
from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger

from app.auth.dependencies import get_current_user
from app.configs.celery_config import celery
from app.enum.analysis import AnalysisType
from app.enum.experience import Experience
from app.models.users import User as UserModel
from app.tasks.vacancy_tasks import ai_analyse_task, clear_lock, import_vacancy_task


router = APIRouter(prefix="/tasks")

TAGS = "Tasks_v2"


LOCK_REDIS_URL = os.getenv("LOCK_REDIS_URL")
redis_client = redis.from_url(LOCK_REDIS_URL, decode_responses=True)


@router.post(
    "/import_vacancies",
    status_code=status.HTTP_202_ACCEPTED,
    tags=[TAGS],
    summary="Импорт вакансий с hh.ru в фоновом режиме",
)
async def task_import_vacancies(
    query: str,
    tiers: list[Experience] | None = Query(
        None,
        description="Фильтрация по уровню опыта. Можно выбрать несколько значений. Если не указано - возвращаются все вакансии.",
    ),
    current_user: UserModel = Depends(get_current_user),
) -> dict[str, str]:
    """
    Запускает импорт вакансий с hh.ru в фоновом режиме.

    Использует Redis distributed locks для предотвращения дубликатов:
    - Одинаковый query для одного пользователя → один lock
    - Lock автоматически удаляется после завершения задачи

    Примеры запросов:
    - django OR fastapi OR aiohttp OR litestar OR flask OR sanic OR tornado

    Фильтрация по уровню опыта (tiers):
    - noExperience: Без опыта
    - between1And3: От 1 до 3 лет
    - between3And6: От 3 до 6 лет
    - moreThan6: Более 6 лет
    """

    # Формируем уникальный task_id и lock_key
    task_id = f"import:{current_user.id}:{query}"
    lock_key = f"active:{task_id}"

    # Проверяем есть ли активная задача
    active_lock = redis_client.get(lock_key)
    if active_lock:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "Импорт уже запущен",
                "message": "Дождитесь завершения текущей задачи или повторите запрос позже",
                "task_id": task_id,
            },
        )

    # Ставим блокировку на 5 минут (автоудаление если задача упадёт)
    redis_client.setex(lock_key, 300, "1")

    logger.info(f"Запущена фоновая задача {task_id} для импорта вакансий по запросу: {query}")

    # Запускаем задачу с callback для удаления блокировки
    task = import_vacancy_task.apply_async(
        args=[query, tiers, current_user.id],
        task_id=task_id,
        link=clear_lock.s(lock_key),  # Удалить блокировку после завершения
    )

    return {
        "task_id": task.id,
        "status": task.state,
        "query": query,
    }


@router.get(
    "/{task_id}",
    status_code=status.HTTP_200_OK,
    tags=[TAGS],
    summary="Проверить статус задачи",
)
async def get_task_status(task_id: str, current_user: UserModel = Depends(get_current_user)) -> dict[str, Any]:
    """
    Проверяет статус выполнения Celery задачи.

    Возвращает:
    - task_id: ID задачи
    - status: PENDING | STARTED | SUCCESS | FAILURE | RETRY
    - result: результат (если задача завершена)
    - error: ошибка (если задача упала)
    """
    result = AsyncResult(task_id, app=celery)

    # Проверяем что пользователь имеет доступ к задаче
    task_user_id = None
    if result.successful() and isinstance(result.result, dict):
        task_user_id = result.result.get("user_id")

    if task_user_id and task_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    response = {
        "task_id": task_id,
        "status": result.state,
    }

    if result.successful():
        response["result"] = result.result
    elif result.failed():
        response["error"] = str(result.info)
    elif result.state == "PROGRESS":
        response["progress"] = result.info

    return response


@router.post(
    "/analysis_vacancies",
    status_code=status.HTTP_202_ACCEPTED,
    tags=[TAGS],
    summary="Анализ вакансий с hh.ru в фоновом режиме",
)
async def task_analysis_vacancies(
    limit: int,
    analysis: list[AnalysisType] = Query(
        description="Фильтрация по типу анализа. Можно выбрать несколько значений.",
    ),
    tiers: list[Experience] | None = Query(
        None,
        description="Фильтрация по уровню опыта. Можно выбрать несколько значений. Если не указано - возвращаются все вакансии.",
    ),
    custom_prompt: str | None = None,
    current_user: UserModel = Depends(get_current_user),
) -> dict[str, str]:
    """
    Запускает анализ вакансий в фоновом режиме.

    Использует Redis distributed locks для предотвращения дубликатов.
    """

    if AnalysisType.CUSTOM in analysis and not custom_prompt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="custom_prompt is required for CUSTOM type")

    # Формируем уникальный task_id и lock_key
    analysis_str = ",".join([a.value for a in analysis])
    task_id = f"analysis:{current_user.id}:{analysis_str}:{limit}"
    lock_key = f"active:{task_id}"

    # Проверяем есть ли активная задача
    active_lock = redis_client.get(lock_key)
    if active_lock:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "Анализ уже запущен",
                "message": "Дождитесь завершения текущей задачи",
                "task_id": task_id,
            },
        )

    # Ставим блокировку на 5 минут
    redis_client.setex(lock_key, 300, "1")

    # Запускаем задачу
    task = ai_analyse_task.apply_async(
        args=[analysis, tiers, current_user.id, custom_prompt, limit],
        task_id=task_id,
        link=clear_lock.s(lock_key),
    )

    logger.info(f"Запущена фоновая задача {task_id} для анализа вакансий: {analysis}")

    return {
        "task_id": task.id,
        "status": task.state,
        "analysis": analysis_str,
    }
