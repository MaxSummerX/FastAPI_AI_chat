from typing import cast

import bcrypt


def hash_password(password: str) -> str:
    """
    Преобразует пароль в хеш с использованием bcrypt.
    """
    # Генерируем соль в байтах
    salt = bcrypt.gensalt(rounds=12)
    # Получаем хэш пароля в байтах с использованием соли
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    # Возвращаем сам хэш пароля
    return cast(str, hashed.decode("utf-8"))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Проверяет, соответствует ли введённый пароль сохранённому хешу.
    """
    # Преобразуем в байты
    hashed_bytes = hashed_password.encode("utf-8")
    # Возвращаем результат проверки пароля
    return cast(bool, bcrypt.checkpw(plain_password.encode("utf-8"), hashed_bytes))
