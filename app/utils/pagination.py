import base64
import json
from datetime import datetime
from uuid import UUID

from loguru import logger
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import InvalidCursorError


DEFAULT_PER_PAGE = 20
MINIMUM_PER_PAGE = 1
MAXIMUM_PER_PAGE = 100
DEFAULT_OFFSET = 0


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


async def paginate_with_cursor[T](
    db: AsyncSession,
    query: Select,
    cursor: str | None,
    limit: int,
    model: type[T],
    timestamp_field: str = "created_at",
) -> tuple[list[T], str | None, bool]:
    """
    Универсальная курсорная пагинация для моделей с timestamp полем + id.

    Args:
        db: Сессия БД
        query: Базовый запрос с фильтрами (без order_by/limit)
        cursor: Курсор из предыдущего ответа
        limit: Размер страницы
        model: Модель SQLAlchemy (должна иметь timestamp_field и id)
        timestamp_field: Имя поля с timestamp (по умолчанию "created_at",
                        для MessageModel использовать "timestamp")

    Returns:
        (items, next_cursor, has_next)
    """
    limit = validate_pagination_limit(limit)

    # Получаем атрибут timestamp из модели динамически
    timestamp_attr = getattr(model, timestamp_field)

    # 1. Применяем курсор (если есть)
    if cursor:
        try:
            timestamp, cursor_id_str = decode_cursor(cursor)
            cursor_uuid = UUID(cursor_id_str)
            query = query.where(
                (timestamp_attr < timestamp) | ((timestamp_attr == timestamp) & (model.id < cursor_uuid))  # type: ignore[attr-defined]
            )
        except (ValueError, KeyError) as e:
            raise InvalidCursorError(f"Invalid cursor format: {e}") from e

    # 2. Сортировка
    query = query.order_by(timestamp_attr.desc(), model.id.desc())  # type: ignore[attr-defined]

    result = await db.scalars(query.limit(limit + 1))
    items = list(result.all())

    # 4. Обрезка и next_cursor
    has_next = calculate_has_more(items, limit)
    items = trim_excess_item(items, limit, reverse=False)

    next_cursor = None
    if items and has_next:
        last_item = items[-1]
        last_timestamp = getattr(last_item, timestamp_field)
        next_cursor = encode_cursor(last_timestamp, last_item.id)

    return items, next_cursor, has_next
