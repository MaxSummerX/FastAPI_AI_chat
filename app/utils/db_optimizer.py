from typing import Literal, TypeVar

from pydantic import BaseModel
from sqlalchemy import Select, select
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import DeclarativeBase, joinedload, load_only, selectinload


T = TypeVar("T", bound=DeclarativeBase)
S = TypeVar("S", bound=BaseModel)


def optimized_query[T: DeclarativeBase, S: BaseModel](
    model: type[T],
    schema: type[S],
    relationship_strategy: Literal["joined", "selectin"] = "selectin",
    include_unloaded: bool = False,
) -> Select[T]:
    """
    Создает оптимизированный SQLAlchemy запрос на основе Pydantic схемы

    Args:
        model: SQLAlchemy модель
        schema: Pydantic схема для определения загружаемых полей
        relationship_strategy: Стратегия загрузки relationships
            - "joined": JOIN запрос (быстрее для малого кол-ва связей)
            - "selectin": Отдельные запросы (лучше для множественных связей)
        include_unloaded: Включать ли поля модели, отсутствующие в схеме

    Returns:
        SQLAlchemy Select statement с оптимизированными options
    """
    mapper = inspect(model)

    # 1. Обязательно включаем Primary Key
    pk_columns = {pk.key for pk in mapper.primary_key}

    # 2. Анализируем поля схемы
    schema_fields = schema.model_fields.keys()
    columns_to_load = set()
    relationships_to_load = []

    for field_name in schema_fields:
        if not hasattr(model, field_name):
            continue

        attr = getattr(model, field_name)

        # Проверяем тип атрибута
        if hasattr(attr, "property"):
            if hasattr(attr.property, "mapper"):
                # Это relationship
                relationships_to_load.append(field_name)
            else:
                # Это обычная колонка
                columns_to_load.add(field_name)

    # 3. Добавляем PK к загружаемым колонкам
    columns_to_load |= pk_columns

    # 4. Формируем запрос
    stmt = select(model)

    # 5. Применяем load_only для колонок
    if columns_to_load and not include_unloaded:
        column_attrs = [getattr(model, col) for col in columns_to_load]
        stmt = stmt.options(load_only(*column_attrs))

    # 6. Применяем eager loading для relationships
    for rel_name in relationships_to_load:
        rel_attr = getattr(model, rel_name)

        if relationship_strategy == "joined":
            stmt = stmt.options(joinedload(rel_attr))
        else:
            stmt = stmt.options(selectinload(rel_attr))

    return stmt
