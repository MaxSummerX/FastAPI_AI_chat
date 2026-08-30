"""Сервисные исключения для работы с пользователями.

Модуль содержит кастомные исключения для бизнес-логики UserService.
Каждое исключение описывает конкретную ошибку при операциях с пользователями.
"""

from app.application.exceptions.base import BaseAppException


class UserNotFoundException(BaseAppException):
    """Пользователь не найден в базе данных.

    Возникает при попытке получить пользователя по-несуществующему ID или username.
    """


class IncorrectPasswordException(BaseAppException):
    """Неверный пароль при аутентификации.

    Возникает когда предоставленный пароль не совпадает с хешем в БД.
    """


class UsernameAlreadyExistsException(BaseAppException):
    """Username уже занят другим пользователем.

    Возникает при регистрации или попытке изменить username на существующий.
    """


class EmailAlreadyExistsException(BaseAppException):
    """Email уже занят другим пользователем.

    Возникает при регистрации или попытке изменить email на существующий.
    """


class UserAlreadyAdminException(BaseAppException):
    """Пользователь уже имеет роль администратора.

    Возникает при попытке повысить права пользователя, который уже админ.
    """


class SamePasswordException(BaseAppException):
    """Новый пароль совпадает с текущим.

    Возникает при попытке сменить пароль на тот же самый.
    """


class SameEmailException(BaseAppException):
    """Новый email совпадает с текущим.

    Возникает при попытке изменить email на то же самое значение.
    """


class SameUsernameException(BaseAppException):
    """Новый username совпадает с текущим.

    Возникает при попытке изменить username на то же самое значение.
    """
