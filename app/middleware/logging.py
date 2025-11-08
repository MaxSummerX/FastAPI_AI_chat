from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from loguru import logger


logger.add("log_info.log", format="Log: [{extra[log_id]}:{time} - {level} - {message}]", level="INFO", enqueue=True)


async def log_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """
    Middleware для логирования HTTP запросов с уникальным ID
    """

    log_id = str(uuid4())

    with logger.contextualize(log_id=log_id):
        try:
            # Логируем входящий запрос
            logger.info(f"-> {request.method} {request.url.path}")

            # Обрабатываем запрос
            response = await call_next(request)

            if response.status_code >= 400:
                logger.warning(f"← {request.method} {request.url.path} [{response.status_code}] FAILED")
            else:
                logger.info(f"← {request.method} {request.url.path} [{response.status_code}] SUCCESS")

            return response

        except Exception as ex:
            logger.error(f"✗ {request.method} {request.url.path} ERROR: {ex}", exc_info=True)
            return JSONResponse(content={"success": False, "error": str(ex)}, status_code=500)
