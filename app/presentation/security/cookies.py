"""
Работа с cookie аутентификации.

Refresh-токен передаётся только через httpOnly cookie —
недоступен JavaScript, что исключает кражу через XSS.
"""

from fastapi import Response

from app.infrastructure.settings.settings import settings


REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/user/refresh-token"
REFRESH_COOKIE_TTL = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600


def set_refresh_cookie(response: Response, token: str) -> None:
    """Ставит httpOnly cookie с refresh-токеном (недоступен JS — защита от XSS)."""
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="strict",
        max_age=REFRESH_COOKIE_TTL,
        path=REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response: Response) -> None:
    """Удаляет cookie с refresh-токеном (логаут)."""
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
