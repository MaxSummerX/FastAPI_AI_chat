import base64
import json
from datetime import datetime
from uuid import UUID

from loguru import logger


DEFAULT_PER_PAGE = 20
MAXIMUM_PER_PAGE = 100


def encode_cursor(timestamp: datetime, id_uuid: UUID) -> str:
    """
    Кодирует курсор из timestamp и id_uuid в base64 строку.

    Курсор используется для запоминания позиции в наборе данных при пагинации.
    Кодирование в base64 позволяет безопасно передавать курсор в URL параметрах.
    """
    # Валидация входных данных
    if not isinstance(timestamp, datetime):
        raise ValueError(f"timestamp must be datetime, got {type(timestamp)}")

    if isinstance(id_uuid, UUID):
        id_str = str(id_uuid)
    elif isinstance(id_uuid, str):
        id_str = id_uuid
    else:
        raise ValueError(f"id_uuid must be UUID or str, got {type(id_uuid)}")

    # Формируем данные для кодирования
    data = {
        "timestamp": timestamp.isoformat(),
        "id_str": id_str,
    }

    # Кодируем в JSON, затем в base64
    json_str = json.dumps(data, separators=(",", ":"))
    cursor_bytes = json_str.encode("utf-8")
    encoded = base64.b64encode(cursor_bytes).decode("ascii")

    logger.debug(f"Encoded cursor: timestamp={timestamp}, id={id_str} -> {encoded[: min(20, len(encoded))]}...")

    return encoded


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    """
    Декодирует курсор из base64 строки в timestamp и id_uuid

    Обратная функция для encode_cursor. Извлекает закодированные данные
    о позиции в наборе данных.
    """
    if not cursor or not isinstance(cursor, str):
        raise ValueError(f"cursor must be non-empty string, got {type(cursor)}")
    try:
        # Декодируем из base64
        encoded_bytes = cursor.encode("ascii")
        decoded_bytes = base64.b64decode(encoded_bytes)
        json_str = decoded_bytes.decode("utf-8")

        # Парсим JSON
        data = json.loads(json_str)

        # Извлекаем данные
        timestamp_str = data["timestamp"]
        id_str = data["id_str"]

        # Конвертируем timestamp
        timestamp = datetime.fromisoformat(timestamp_str)

        logger.debug(f"Decoded cursor: {cursor[: min(20, len(cursor))]}... -> timestamp={timestamp}, id={id_str}")

        return timestamp, id_str

    except (KeyError, json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"Invalid cursor format: {e}") from e

    except Exception as e:
        raise ValueError(f"Failed to decode cursor: {e}") from e


def validate_pagination_limit(
    limit: int | None, default: int = DEFAULT_PER_PAGE, maximum: int = MAXIMUM_PER_PAGE
) -> int:
    """
    Валидирует и нормализует параметр limit для пагинации.

    Ограничивает размер страницы разумными пределами для защиты
    от излишней нагрузки на базу данных.
    """
    if limit is None or limit <= 0:
        return default

    return min(max(1, limit), maximum)


def validate_cursor_pagination_param(
    limit: int | None,
    before: str | None = None,
    after: str | None = None,
    default_limit: int = DEFAULT_PER_PAGE,
    max_limit: int = MAXIMUM_PER_PAGE,
) -> tuple[int, tuple[datetime, str] | None, bool]:
    """
    Валидирует параметры для двунаправленной курсорной пагинации.

    Проверяет, что параметры корректны и возвращает декодированный курсор.
    """
    # Проверка на взаимоисключающие параметры
    if before and after:
        raise ValueError("'before' and 'after' parameters are mutually exclusive")

    # Валидируем limit
    limit = validate_pagination_limit(limit, default_limit, max_limit)

    # Декодируем курсор если есть
    decoded_cursor: tuple[datetime, str] | None = None
    reverse_order = False

    if before:
        decoded_cursor = decode_cursor(before)
        reverse_order = True
    elif after:
        decoded_cursor = decode_cursor(after)
        reverse_order = True
    else:
        # Первая загрузка — берём последние элементы
        reverse_order = True

    return limit, decoded_cursor, reverse_order


def calculate_has_more(items: list, limit: int) -> bool:
    """
    Определяет, есть ли ещё элементы после текущей страницы.

    Работает на основе того факта, что мы запрашиваем на один элемент больше,
    чем нужно. Если вернулось больше элементов, чем limit — есть следующая страница.
    """
    return len(items) > limit


def trim_excess_item(items: list, limit: int, reverse: bool = False) -> list:
    """
    Убирает лишний элемент из списка и разворачивает если нужно.

    При проверке has_more мы запрашиваем limit + 1 элементов.
    Если лишний элемент есть — убираем его. Также разворачиваем список
    при необходимости.
    """
    result = items[:limit] if len(items) > limit else items

    if reverse:
        result = list(reversed(result))

    return result
