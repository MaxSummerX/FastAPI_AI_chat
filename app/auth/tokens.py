from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import jwt

from app.config import ALGORITHM, SECRET_KEY


ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7


def create_access_token(data: dict) -> str:
    """
    Создаёт JWT с payload (sub, role, id, exp).
    """
    # Создаём копию входного словаря
    to_encode = data.copy()

    # Преобразуем UUID в строку
    for key, value in to_encode.items():
        if isinstance(value, UUID):
            to_encode[key] = str(value)

    # Вычисляет время истечения токена
    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    # Добавляет поле exp (expiration) в payload токена
    to_encode.update({"exp": expire})
    # Возвращаем строку токена
    return cast(str, jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM))


def create_refresh_token(data: dict) -> str:
    """
    Создаёт refresh-токен с длительным сроком действия.
    """
    # Создаём копию входного словаря
    to_encode = data.copy()

    # Преобразуем UUID в строку
    for key, value in to_encode.items():
        if isinstance(value, UUID):
            to_encode[key] = str(value)

    # Вычисляет время истечения токена
    expire = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    # Добавляет поле exp (expiration) в payload токена
    to_encode.update({"exp": expire})
    # Возвращаем строку токена
    return cast(str, jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM))
