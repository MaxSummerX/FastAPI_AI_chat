"""
JWT сервис для работы с токенами.

Модуль предоставляет функции для создания и декодирования JWT токенов.
Использует settings для конфигурации секретного ключа и алгоритма шифрования.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.infrastructure.settings.settings import settings


SECRET_KEY = settings.SECRET_KEY.get_secret_value()
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS = settings.REFRESH_TOKEN_EXPIRE_DAYS


@dataclass(frozen=True)
class TokenPayload:
    """
    Полезная нагрузка JWT токена.

    Содержит идентификационные данные пользователя, закодированные в токене.
    Frozen dataclass предотвращает случайные изменения.

    Attributes:
        sub: Username пользователя (subject)
        id: Уникальный идентификатор пользователя
        email: Email пользователя
        role: Роль пользователя
        jti: Уникальный идентификатор токена (для refresh токенов)
    """

    sub: str
    id: str
    email: str
    role: str
    jti: str | None = None


def _create_token(payload: TokenPayload, expires_delta: timedelta) -> str:
    """
    Создаёт JWT токен с указанным сроком действия.

    Внутренняя функция для генерации токенов. Кодирует payload в JWT
    с добавлением времени истечения (exp) и времени создания (iat).

    Args:
        payload: Данные для кодирования в токен
        expires_delta: Срок действия токена

    Returns:
        Закодированный JWT токен (строка)
    """
    expire = datetime.now(UTC) + expires_delta

    claims: dict[str, Any] = {
        "sub": payload.sub,
        "id": payload.id,
        "email": payload.email,
        "role": payload.role,
        "exp": expire,
        "iat": datetime.now(UTC),
    }

    if payload.jti:
        claims["jti"] = payload.jti

    return str(jwt.encode(claims, SECRET_KEY, ALGORITHM))


def create_access_token(username: str, user_id: str, email: str, role: str) -> str:
    """
    Создаёт access токен для аутентификации.

    Access токен используется для доступа к защищённым эндпоинтам API.
    Имеет короткий срок действия (по умолчанию 30 минут).

    Args:
        username: Имя пользователя
        user_id: Уникальный идентификатор
        email: Email пользователя
        role: Роль пользователя

    Returns:
        Закодированный JWT access токен
    """
    payload = TokenPayload(sub=username, id=user_id, email=email, role=role)
    return _create_token(payload, timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))


def create_refresh_token(username: str, user_id: str, email: str, role: str, jti: str | None = None) -> str:
    """
    Создаёт refresh токен для обновления access токена.

    Refresh токен имеет длительный срок действия (по умолчанию 7 дней)
    и используется для получения новых access токенов без повторной аутентификации.
    Содержит уникальный jti для отслеживания и возможности отзыва.

    Args:
        username: Имя пользователя
        user_id: Уникальный идентификатор
        email: Email пользователя
        role: Роль пользователя
        jti: Уникальный идентификатор токена (опционально)

    Returns:
        Закодированный JWT refresh токен
    """
    payload = TokenPayload(sub=username, id=user_id, email=email, role=role, jti=jti)
    return _create_token(payload, timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))


def decode_token(token: str) -> TokenPayload:
    """
    Декодирует и валидирует JWT токен.

    Проверяет подпись, срок действия и извлекает данные из токена.
    При ошибке валидации выбрасывает jwt.PyJWTError.

    Args:
        token: JWT токен для декодирования

    Returns:
        TokenPayload с данными из токена

    Raises:
        jwt.ExpiredSignatureError: Если токен истёк
        jwt.PyJWTError: Если токен невалиден или подпись не совпадает
    """
    claim = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    return TokenPayload(
        sub=claim["sub"],
        id=claim["id"],
        email=claim["email"],
        role=claim["role"],
        jti=claim.get("jti"),
    )
