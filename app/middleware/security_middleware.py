# Security Headers Middleware
from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from app.configs.settings import settings


async def add_security_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
    """
    Добавляет security headers к ответам для повышения безопасности
    """
    response = await call_next(request)

    # Добавляем security headers только в продакшене
    if not settings.is_development:
        # Защита от Clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Защита от MIME-sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Защита от XSS
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Политика реферера
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Content Security Policy
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self' wss: ws: https://api.openai.com https://openrouter.ai;"
        )

        # HSTS (только для HTTPS)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Permissions Policy (бывший Feature Policy)
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=(), payment=(), usb=()"

    return response
