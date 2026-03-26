from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field


# Типовая переменная для элементов в пагинированном ответе
T = TypeVar("T")


DEFAULT_PER_PAGE = 20
MINIMUM_PER_PAGE = 1
MAXIMUM_PER_PAGE = 100


class PaginationParams(BaseModel):
    """
    Параметры пагинации из query string

    Используется как dependency в FastAPI endpoint'ах для валидации
    параметров пагинации из URL query parameters.
    """

    limit: int = Field(
        default=DEFAULT_PER_PAGE,
        ge=MINIMUM_PER_PAGE,
        le=MAXIMUM_PER_PAGE,
        description="Размер страницы. Минимум: 1, Максимум: 100, По умолчанию: 20",
    )
    cursor: str | None = Field(
        default=None,
        description=(
            "Курсор для получения следующей страницы."
            "Возвращается в предыдущем ответе в поле next_cursor."
            "Кодируется в base64 формата JSON."
        ),
    )


class CursorPaginationParams(BaseModel):
    """
    Параметры двунаправленной курсорной пагинации

    Используется для сообщений и других данных, где нужна навигация
    в обе стороны (вперёд/назад во времени).
    """

    limit: int = Field(
        default=DEFAULT_PER_PAGE,
        ge=MINIMUM_PER_PAGE,
        le=MAXIMUM_PER_PAGE,
        description="Размер страницы. Минимум: 1, Максимум: 100, По умолчанию: 20",
    )
    before: str | None = Field(
        default=None, description="Курсор для загрузки более старых элементов (прокрутка вверх/назад)"
    )
    after: str | None = Field(
        default=None, description="Курсор для загрузки более новых элементов (прокрутка вниз/вперёд)"
    )


class PaginatedResponse[T](BaseModel):
    """
    Стандартный ответ с пагинацией

    Generic класс, который может содержать любые элементы данных.
    """

    items: list[T] = Field(description="Элементы текущей страницы. Тип зависит от конкретного endpoint'а.")
    next_cursor: str | None = Field(
        default=None, description="Курсор для получения следующей страницы. Если None — достигнут конец данных."
    )
    has_next: bool = Field(default=False, description="Флаг, указывающий есть ли следующая страница данных.")

    model_config = ConfigDict(from_attributes=True)


class BidirectionalPaginatedResponse[T](BaseModel):
    """
    Ответ с двунаправленной пагинацией

    Используется для сообщений чата, где нужна навигация в обе стороны:
    - Загрузка более старых сообщений (история)
    - Загрузка более новых сообщений (новые после последнего запроса)
    """

    items: list[T] = Field(
        description="Список элементов текущей страницы. Для сообщений упорядочен от старого к новому."
    )
    next_cursor: str | None = Field(
        default=None,
        description=(
            "Курсор для загрузки более старых элементов (история). "
            "Для сообщений — более старые сообщения (назад во времени)."
        ),
    )
    prev_cursor: str | None = Field(
        default=None,
        description=(
            "Курсор для загрузки более новых элементов (будущее). "
            "Для сообщений — более новые сообщения (вперёд во времени)."
        ),
    )
    has_next: bool = Field(default=False, description="Есть ли более старые элементы (история)")
    has_prev: bool = Field(default=False, description="Есть ли более новые элементы (будущее)")

    model_config = ConfigDict(from_attributes=True)
