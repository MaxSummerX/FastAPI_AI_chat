import os
from typing import Any

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_shutdown
from dotenv import load_dotenv


load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL") or (REDIS_URL + "/1" if REDIS_URL else None)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND") or (REDIS_URL + "/2" if REDIS_URL else None)


if not CELERY_BROKER_URL:
    raise ValueError("CELERY_BROKER_URL не задан! Установи переменную окружения или REDIS_URL")

if not CELERY_RESULT_BACKEND:
    raise ValueError("CELERY_RESULT_BACKEND не задан! Установи переменную окружения или REDIS_URL")


celery = Celery(
    "ai_chat_tasks",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    broker_connection_retry_on_startup=True,
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1800,  # 30 минут
    worker_prefetch_multiplier=1,  # Не забирать задачи заранее
    worker_max_tasks_per_child=100,  # Рестарт воркера после N задач
    imports=[
        "app.tasks.vacancy_tasks",
    ],
    beat_schedule={
        # Пример: 3 раза в день (каждые 8 часов)
        "periodic-vacancy-import": {
            "task": "app.tasks.vacancy_tasks.import_vacancy_task",
            "schedule": crontab(hour="*/8"),  # 00:00, 08:00, 16:00
            "args": (
                "django OR fastapi OR aiohttp OR litestar OR flask OR sanic OR tornado",
                None,
                "USER_ID",
            ),  # TODO: заменить на реальный user_id
        },
        # Пример: 5 раз в день в конкретное время
        "periodic-vacancy-import-time": {
            "task": "app.tasks.vacancy_tasks.import_vacancy_task",
            "schedule": crontab(hour="6,10,14,18,22"),  # 06:00, 10:00, 14:00, 18:00, 22:00
            "args": ("django OR fastapi OR aiohttp OR litestar OR flask OR sanic OR tornado", None, "USER_ID"),
        },
    },
)


@celery.on_after_configure.connect
def warmup_http_clients(**kwargs: Any) -> None:
    """
    Прогрев HTTP соединений при старте Celery воркера.

    Срабатывает после конфигурации Celery, но до обработки задач.
    Выполняет первый запрос к API hh.ru для установления TLS соединения.
    """
    import asyncio

    async def _warmup() -> None:
        from app.tools.headhunter.headhunter_client import warmup_hh_client

        await warmup_hh_client()

    asyncio.run(_warmup())


@worker_shutdown.connect
def shutdown_http_clients(**kwargs: Any) -> None:
    """
    Закрытие HTTP клиентов при shutdown воркера.

    Срабатывает при корректном завершении работы Celery воркера
    (SIGTERM, SIGINT). Закрывает HTTP соединения для освобождения ресурсов.
    """
    import asyncio

    async def _shutdown() -> None:
        from app.tools.headhunter.headhunter_client import close_hh_client

        await close_hh_client()

    asyncio.run(_shutdown())
