from celery import Celery

# from celery.schedules import crontab
from app.infrastructure.settings.settings import settings


REDIS_URL = settings.REDIS_URL
CELERY_BROKER_URL = settings.CELERY_BROKER_URL
CELERY_RESULT_BACKEND = settings.CELERY_RESULT_BACKEND


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
        "app.infrastructure.task_queue.tasks.vacancy_tasks",
    ],
    beat_schedule={
        # "periodic-vacancy-import": {
        #     "task": "app.infrastructure.task_queue.tasks.vacancy_tasks.import_vacancy_task",
        #     "schedule": crontab(hour="*/8"),  # 00:00, 08:00, 16:00
        #     "args": (
        #         "django OR fastapi OR aiohttp OR litestar OR flask OR sanic OR tornado",
        #         None,
        #         "USER_ID",
        #     ),  # TODO: заменить на реальный user_id
        # },
        # "periodic-vacancy-import-time": {
        #     "task": "app.infrastructure.task_queue.tasks.vacancy_tasks.import_vacancy_task",
        #     "schedule": crontab(hour="6,10,14,18,22"),  # 06:00, 10:00, 14:00, 18:00, 22:00
        #     "args": ("django OR fastapi OR aiohttp OR litestar OR flask OR sanic OR tornado", None, "USER_ID"),
        # },
    },
)
