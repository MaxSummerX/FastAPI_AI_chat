"""
Redis-клиенты для распределённых замков.

- redis_async — для API (FastAPI, lifespan управляет жизненным циклом)
- redis_sync — для celery-воркера (в task_queue sync-код)

Замки живут в отдельном Redis (LOCK_REDIS_URL), не в брокере celery.
"""

import redis
import redis.asyncio as redis_asyncio

from app.infrastructure.settings.settings import settings


redis_async: redis_asyncio.Redis = redis_asyncio.from_url(settings.LOCK_REDIS_URL, decode_responses=True)
redis_sync: redis.Redis = redis.from_url(settings.LOCK_REDIS_URL, decode_responses=True)


async def ping_redis() -> bool:
    """Проверка доступности Redis. False — если недоступен."""
    try:
        return bool(await redis_async.ping())
    except Exception:
        return False
