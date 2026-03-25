"""
Сервис хэширования паролей.

Модуль предоставляет функции для безопасного хэширования и проверки паролей
с использованием bcrypt. Stateless функции без зависимости от глобального состояния.
"""

import bcrypt


def hash_password(password: str) -> str:
    """
    Преобразует пароль в хеш с использованием bcrypt.

    Генерирует уникальную соль и создаёт хеш пароля с 12 раундами.
    Результат можно безопасно хранить в базе данных.

    Args:
        password: Открытый пароль для хэширования

    Returns:
        Хэш пароля в формате bcrypt (строка, начинается с $2b$12$)
    """
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    result: str = hashed.decode("utf-8")
    return result


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Проверяет, соответствует ли введённый пароль сохранённому хешу.

    Безопасно сравнивает открытый пароль с хэшем, защищая от timing attacks.

    Args:
        plain_password: Открытый пароль для проверки
        hashed_password: Хэш пароля из базы данных

    Returns:
        True если пароль соответствует хешу, False в противном случае
    """
    hashed_bytes = hashed_password.encode("utf-8")
    is_valid: bool = bcrypt.checkpw(plain_password.encode("utf-8"), hashed_bytes)
    return is_valid
