"""
Глобальные exception handlers: маппинг доменных исключений в HTTP-ответы.
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from loguru import logger

from app.application.exceptions.analysis import InvalidAnalysisTypeError
from app.application.exceptions.auth import (
    InvalidCredentialsException,
    InvalidInviteCodeException,
    InvalidTokenException,
    TokenExpiredException,
    UserAlreadyExistsException,
)
from app.application.exceptions.base import BaseAppException
from app.application.exceptions.conversation import ConversationNotFoundError
from app.application.exceptions.document import DocumentNotFoundError
from app.application.exceptions.fact import (
    FactCreationException,
    FactNotFoundException,
    UserProvidedException,
)
from app.application.exceptions.llm import LLMError
from app.application.exceptions.prompt import PromptNotFoundError
from app.application.exceptions.user import (
    EmailAlreadyExistsException,
    IncorrectPasswordException,
    SameEmailException,
    SamePasswordException,
    SameUsernameException,
    UserAlreadyAdminException,
    UsernameAlreadyExistsException,
    UserNotFoundException,
)
from app.application.exceptions.vacancy import (
    AnalysisAlreadyExistsError,
    AnalysisNotFoundError,
    InvalidVacancyCursorError,
    ResumeRequiredError,
    ResumeTooShortError,
    VacancyFetchError,
    VacancyImportError,
    VacancyNotFoundError,
)
from app.infrastructure.persistence.pagination import InvalidCursorError


STATUS_MAP: dict[type[BaseAppException], int] = {
    # 400
    InvalidAnalysisTypeError: status.HTTP_400_BAD_REQUEST,
    InvalidVacancyCursorError: status.HTTP_400_BAD_REQUEST,
    ResumeTooShortError: status.HTTP_400_BAD_REQUEST,
    SameEmailException: status.HTTP_400_BAD_REQUEST,
    SamePasswordException: status.HTTP_400_BAD_REQUEST,
    SameUsernameException: status.HTTP_400_BAD_REQUEST,
    # 401 / 403
    InvalidCredentialsException: status.HTTP_401_UNAUTHORIZED,
    IncorrectPasswordException: status.HTTP_401_UNAUTHORIZED,
    InvalidTokenException: status.HTTP_401_UNAUTHORIZED,
    TokenExpiredException: status.HTTP_401_UNAUTHORIZED,
    InvalidInviteCodeException: status.HTTP_403_FORBIDDEN,
    UserProvidedException: status.HTTP_403_FORBIDDEN,
    # 404
    UserNotFoundException: status.HTTP_404_NOT_FOUND,
    ConversationNotFoundError: status.HTTP_404_NOT_FOUND,
    DocumentNotFoundError: status.HTTP_404_NOT_FOUND,
    FactNotFoundException: status.HTTP_404_NOT_FOUND,
    PromptNotFoundError: status.HTTP_404_NOT_FOUND,
    VacancyNotFoundError: status.HTTP_404_NOT_FOUND,
    AnalysisNotFoundError: status.HTTP_404_NOT_FOUND,
    # 409
    UserAlreadyExistsException: status.HTTP_409_CONFLICT,
    UsernameAlreadyExistsException: status.HTTP_409_CONFLICT,
    EmailAlreadyExistsException: status.HTTP_409_CONFLICT,
    AnalysisAlreadyExistsError: status.HTTP_409_CONFLICT,
    UserAlreadyAdminException: status.HTTP_409_CONFLICT,
    # 422
    ResumeRequiredError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    # 502 - сбой внешней системы (hh.ru / mem0)
    VacancyFetchError: status.HTTP_502_BAD_GATEWAY,
    VacancyImportError: status.HTTP_502_BAD_GATEWAY,
    FactCreationException: status.HTTP_502_BAD_GATEWAY,
    # 503 - LLM недоступен
    LLMError: status.HTTP_503_SERVICE_UNAVAILABLE,
}


def register_exception_handlers(app: FastAPI) -> None:
    """Регистрирует глобальный обработчик доменных исключений."""

    @app.exception_handler(BaseAppException)
    async def app_exception_handler(request: Request, exc: BaseAppException) -> JSONResponse:
        """Единый маппинг: ищем класс в таблице с учётом наследования (MRO)."""
        for cls in type(exc).__mro__:
            if cls in STATUS_MAP:
                code = STATUS_MAP[cls]
                break
        else:
            logger.error(f"Отсутствует в STATUS_MAP {type(exc).__name__}: {exc}")
            return JSONResponse(status_code=500, content={"detail": "Internal server error"})

        if code >= 500:
            logger.exception(f"{type(exc).__name__}: {exc}")

        return JSONResponse(status_code=code, content={"detail": str(exc)})

    @app.exception_handler(InvalidCursorError)
    async def cursor_exception_handler(request: Request, exc: InvalidCursorError) -> JSONResponse:
        """Невалидный курсор пагинации → 400."""
        logger.warning(f"Невалидный курсор: {request.url.path}: {exc}")
        return JSONResponse(status_code=400, content={"detail": str(exc)})
