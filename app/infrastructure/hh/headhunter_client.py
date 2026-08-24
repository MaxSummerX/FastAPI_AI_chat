"""
Модуль для работы с HeadHunter.ru.
"""

import asyncio

import httpx
from loguru import logger


# =============================================================================
# Конфигурация hh.ru
# =============================================================================

HH_BASE_URL = "https://hh.ru"
HH_TIMEOUT = 60.0
HH_MAX_PAGES = 20

HH_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
HH_HEADERS = {
    "User-Agent": HH_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
}
HH_MAX_KEEPALIVE_CONNECTIONS = 10
HH_MAX_CONNECTIONS = 20
HH_KEEPALIVE_EXPIRY = 30.0


# =============================================================================
# HTTP Клиент
# =============================================================================

_client: httpx.AsyncClient | None = None
_client_loop_id: int | None = None  # ID event loop в котором создан клиент


async def get_hh_client() -> httpx.AsyncClient:
    """
    Получает или создаёт HTTP клиент для scraping страниц hh.ru.

    Singleton: переиспользует соединения между запросами.
    Закрывается при shutdown приложения (close_hh_client).

    ВАЖНО: Если текущий event loop отличается от того, в котором был создан
    клиент, клиент будет пересоздан. Это необходимо для Celery, где задачи
    могут выполняться в разных event loops.
    """
    global _client, _client_loop_id

    current_loop = asyncio.get_running_loop()
    current_loop_id = id(current_loop)

    # Клиент валиден — возвращаем как есть
    if _client is not None and not _client.is_closed and _client_loop_id == current_loop_id:
        return _client

    # Закрываем старый клиент, если есть
    if _client is not None and not _client.is_closed:
        try:
            await _client.aclose()
        except Exception as e:
            logger.warning(f"Ошибка при закрытии клиента: {e}")

    client = httpx.AsyncClient(
        base_url=HH_BASE_URL,
        timeout=HH_TIMEOUT,
        follow_redirects=True,
        limits=httpx.Limits(
            max_keepalive_connections=HH_MAX_KEEPALIVE_CONNECTIONS,
            max_connections=HH_MAX_CONNECTIONS,
            keepalive_expiry=HH_KEEPALIVE_EXPIRY,
        ),
        headers=HH_HEADERS,
        http2=True,
    )
    _client = client
    _client_loop_id = current_loop_id

    return client


async def close_hh_client() -> None:
    """
    Закрывает HTTP клиент.

    Следует вызывать при shutdown приложения.
    """
    global _client, _client_loop_id

    if _client is not None and not _client.is_closed:
        await _client.aclose()
        _client = None
        _client_loop_id = None
