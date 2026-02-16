"""
Роли пользователей в системе.

Определяет уровень доступа и возможности пользователей.
"""

from enum import StrEnum


class UserRole(StrEnum):
    """
    Роли пользователей.

    Attributes:
        USER: Обычный пользователь с базовыми правами
        ADMIN: Администратор с полным доступом к системе
        MODERATOR: Модератор с расширенными правами модерации
    """

    USER = "user"
    ADMIN = "admin"
    MODERATOR = "moderator"
