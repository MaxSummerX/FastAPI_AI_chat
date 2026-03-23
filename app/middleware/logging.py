from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from loguru import logger


logger.add(
    "log_info.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="INFO",
    enqueue=True,
    backtrace=True,
    diagnose=True,
)


async def log_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """
    Middleware для логирования HTTP запросов с уникальным ID
    """
    log_id = str(uuid4())[:16]  # Короткий ID для удобства

    with logger.contextualize(log_id=log_id):
        try:
            # Логируем входящий запрос с log_id
            logger.info("[{}] -> {} {}", log_id, request.method, request.url.path)

            # Обрабатываем запрос
            response = await call_next(request)

            if response.status_code >= 400:
                logger.warning(
                    "[{}] <- {} {} [{}] FAILED", log_id, request.method, request.url.path, response.status_code
                )
            else:
                logger.info(
                    "[{}] <- {} {} [{}] SUCCESS", log_id, request.method, request.url.path, response.status_code
                )

            return response

        except Exception as ex:
            logger.error("[{}] ✗ {} {} ERROR: {}", log_id, request.method, request.url.path, ex, exc_info=True)
            return JSONResponse(content={"success": False, "error": str(ex)}, status_code=500)
