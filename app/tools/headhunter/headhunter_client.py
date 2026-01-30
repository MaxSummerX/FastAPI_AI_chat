"""
Модуль для работы с API HeadHunter.ru.

Централизованная конфигурация HTTP клиента и API эндпоинтов.
"""

import asyncio
from enum import Enum
from typing import Any

import httpx
from loguru import logger
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


# =============================================================================
# Конфигурация API hh.ru
# =============================================================================

HH_BASE_URL = "https://api.hh.ru"
HH_TIMEOUT = 60.0
HH_REQUEST_DELAY = 0.4  # Задержка между запросами (rate limiting)
HH_MAX_PAGES = 20  # Максимальное количество страниц для пагинации
HH_CONCURRENT_REQUESTS = 5  # Количество одновременных запросов

# Retry настройки
HH_MAX_RETRIES = 3  # Максимальное количество попыток
HH_RETRY_MIN_WAIT = 1.0  # Минимальная задержка между попытками (секунды)
HH_RETRY_MAX_WAIT = 10.0  # Максимальная задержка между попытками (секунды)


class HHApiEndpoint(str, Enum):
    """
    Эндпоинты API hh.ru.

    Все пути относительные от base_url.
    httpx автоматически комбинирует base_url + endpoint.
    """

    VACANCIES = "/vacancies"
    VACANCIES_BY_ID = "/vacancies/{vacancy_id}"
    EMPLOYERS = "/employers"
    EMPLOYER_BY_ID = "/employers/{employer_id}"


# =============================================================================
# HTTP Клиент
# =============================================================================

_client: httpx.AsyncClient | None = None
_client_loop_id: int | None = None  # ID event loop в котором создан клиент


async def get_hh_client() -> httpx.AsyncClient:
    """
    Получает или создаёт HTTP клиент для работы с API hh.ru.

    Использует singleton паттерн для переиспользования соединения.
    Клиент автоматически закрывается при shutdown приложения.

    ВАЖНО: Если текущий event loop отличается от того, в котором был создан
    клиент, клиент будет пересоздан. Это необходимо для Celery, где warmup
    и task выполняются в разных event loops.

    Настройки для устойчивости к timeouts после простоя:
    - Увеличенный keepalive для поддержания соединений
    - HTTP/2 support для улучшенной работы с соединениями
    """
    global _client, _client_loop_id

    current_loop = asyncio.get_running_loop()
    current_loop_id = id(current_loop)

    # Пересоздаём клиент если:
    # 1. Клиента нет
    # 2. Клиент закрыт
    # 3. Текущий event loop отличается от того, в котором создан клиент
    if _client is None or _client.is_closed or _client_loop_id != current_loop_id:
        # Закрываем старый клиент если есть
        if _client is not None and not _client.is_closed:
            try:
                await _client.aclose()
            except Exception:
                pass  # Игнорируем ошибки при закрытии старого клиента

        _client = httpx.AsyncClient(
            base_url=HH_BASE_URL,
            timeout=HH_TIMEOUT,
            limits=httpx.Limits(
                max_keepalive_connections=10,
                max_connections=20,
                keepalive_expiry=30.0,  # Закрывать keepalive через 30 сек простоя
            ),
            headers={
                "User-Agent": "Cortex/0.1",
                "Accept": "application/json",
                "Connection": "keep-alive",
            },
            http2=True,  # HTTP/2 для лучшего мультиплексирования
        )
        _client_loop_id = current_loop_id

    return _client


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


async def warmup_hh_client() -> None:
    """
    Прогревает HTTP соединение с API hh.ru.

    Выполняет лёгкий запрос для установления TCP/TLS соединения.
    Рекомендуется вызывать при старте Celery воркера для избежания
    timeout на первом реальном запросе.
    """
    try:
        client = await get_hh_client()

        # Лёгкий тестовый запрос для установления соединения
        response = await client.get(
            HHApiEndpoint.VACANCIES,
            params={"text": "python", "per_page": 1},
            timeout=10.0,  # Короткий timeout для warmup
        )

        if response.status_code == 200:
            logger.info("✅ HH API client warmed up successfully")
        else:
            logger.warning(f"⚠️ HH API warmup returned status {response.status_code}")

    except Exception as e:
        logger.warning(f"⚠️ HH API warmup failed (non-critical): {e}")
        # Не выбрасываем исключение - warmup это nice-to-have


# =============================================================================
# Retry функции для устойчивости к временным ошибкам
# =============================================================================


def _log_retry_attempt(retry_state: RetryCallState) -> None:
    """Логирует попытку retry."""
    if retry_state.outcome and retry_state.outcome.exception():
        logger.warning(
            f"⚠️ Retry attempt {retry_state.attempt_number}/{HH_MAX_RETRIES} "
            f"after error: {retry_state.outcome.exception()}"
        )


@retry(
    stop=stop_after_attempt(HH_MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=HH_RETRY_MIN_WAIT, max=HH_RETRY_MAX_WAIT),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError)),
    before_sleep=_log_retry_attempt,
    reraise=True,
)
async def hh_get_with_retry(
    client: httpx.AsyncClient,
    endpoint: str,
    **kwargs: Any,
) -> httpx.Response:
    """
    Выполняет GET запрос к API hh.ru с автоматическим retry.

    Ретраит при временных ошибках:
    - TimeoutException - таймаут соединения
    - ConnectError - ошибка подключения (TLS handshake, DNS)
    - RemoteProtocolError - обрыв соединения

    Args:
        client: HTTP клиент
        endpoint: Эндпоинт (например "/vacancies")
        **kwargs: Дополнительные параметры для httpx.get()

    Returns:
        httpx.Response: Ответ от API

    Raises:
        httpx.HTTPError: После исчерпания всех попыток
    """
    response = await client.get(endpoint, **kwargs)
    response.raise_for_status()
    return response


@retry(
    stop=stop_after_attempt(HH_MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=HH_RETRY_MIN_WAIT, max=HH_RETRY_MAX_WAIT),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError)),
    before_sleep=_log_retry_attempt,
    reraise=True,
)
async def hh_post_with_retry(
    client: httpx.AsyncClient,
    endpoint: str,
    **kwargs: Any,
) -> httpx.Response:
    """
    Выполняет POST запрос к API hh.ru с автоматическим retry.

    Аналогично hh_get_with_retry, но для POST запросов.

    Args:
        client: HTTP клиент
        endpoint: Эндпоинт
        **kwargs: Дополнительные параметры для httpx.post()

    Returns:
        httpx.Response: Ответ от API

    Raises:
        httpx.HTTPError: После исчерпания всех попыток
    """
    response = await client.post(endpoint, **kwargs)
    response.raise_for_status()
    return response
