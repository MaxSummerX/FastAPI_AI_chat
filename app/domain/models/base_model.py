"""
Базовый класс для ORM моделей.

Предоставляет общий базовый класс для всех моделей приложения
на основе SQLAlchemy DeclarativeBase.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Базовый класс для всех ORM моделей приложения."""

    pass
