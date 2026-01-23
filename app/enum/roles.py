"""
Роли пользователей в системе.

Определяет уровень доступа и возможности пользователей.
"""

from enum import Enum


class UserRole(str, Enum):
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
