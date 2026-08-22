"""
Зависимости уровня презентации (API layer).

Модуль содержит FastAPI dependency-функции для внедрения зависимостей
в эндпоинты API согласно принципам Dependency Injection и чистой архитектуры.
"""

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from httpx import AsyncClient
from loguru import logger
from mem0 import AsyncMemory
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.auth_service import AuthService
from app.application.services.conversation_service import ConversationService
from app.application.services.document_service import DocumentService
from app.application.services.fact_service import FactService
from app.application.services.invite_service import InviteService
from app.application.services.message_service import MessageService
from app.application.services.prompt_service import PromptService
from app.application.services.upload_service import UploadService
from app.application.services.user_service import UserService
from app.application.services.vacancy_analyzer import VacancyAnalyzer
from app.application.services.vacancy_service import VacancyService
from app.application.services.vacancy_status_service import VacancyArchiveSync
from app.domain.enums.role import UserRole
from app.domain.models.user import User as UserModel
from app.domain.repositories.conversations import IConversationRepository
from app.domain.repositories.documents import IDocumentRepository
from app.domain.repositories.facts import IFactRepository
from app.domain.repositories.invites import IInviteRepository
from app.domain.repositories.messages import IMessageRepository
from app.domain.repositories.prompts import IPromptRepository
from app.domain.repositories.users import IUserRepository
from app.domain.repositories.vacancies import IVacancyRepository
from app.domain.services.llm import ILLMService
from app.domain.services.memory import IMemoryService
from app.infrastructure.database.dependencies import get_db
from app.infrastructure.hh.headhunter_client import get_hh_client
from app.infrastructure.llms.config import base_config_for_llm
from app.infrastructure.llms.factory import create_analysis_llm, create_llm_service
from app.infrastructure.llms.openai import AsyncOpenAILLM
from app.infrastructure.memory.dependencies import create_memory_service, get_memory
from app.infrastructure.persistence.sqlalchemy import (
    ConversationSQLAlchemyRepository,
    DocumentSQLAlchemyRepository,
    InviteSQLAlchemyRepository,
    MessageSQLAlchemyRepository,
    PromptSQLAlchemyRepository,
    UserSQLAlchemyRepository,
    VacancySQLAlchemyRepository,
)
from app.infrastructure.persistence.sqlalchemy.fact_repository import FactsSQLAlchemyRepository
from app.infrastructure.security.jwt_service import TokenPayload, decode_token
from app.infrastructure.settings.settings import settings


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/user/token")


def get_user_repo(db: AsyncSession = Depends(get_db)) -> IUserRepository:
    """
    Создаёт репозиторий пользователей для работы с БД.

    Args:
        db: Асинхронная сессия БД

    Returns:
        IUserRepository: Репозиторий для CRUD операций с пользователями
    """
    return UserSQLAlchemyRepository(db)


def get_invite_repo(db: AsyncSession = Depends(get_db)) -> IInviteRepository:
    """
    Создаёт репозиторий приглашений для работы с БД.

    Args:
        db: Асинхронная сессия БД

    Returns:
        IInviteRepository: Репозиторий для CRUD операций с приглашениями
    """
    return InviteSQLAlchemyRepository(db)


def get_document_repo(db: AsyncSession = Depends(get_db)) -> IDocumentRepository:
    """
    Создаёт репозиторий документов для работы с БД.

    Args:
        db: Асинхронная сессия БД

    Returns:
        IDocumentRepository: Репозиторий для CRUD операций с документами
    """
    return DocumentSQLAlchemyRepository(db)


def get_conversation_repo(db: AsyncSession = Depends(get_db)) -> IConversationRepository:
    """
    Создаёт репозиторий бесед для работы с БД.

    Args:
        db: Асинхронная сессия БД

    Returns:
        IConversationRepository: Репозиторий для CRUD операций с беседами
    """
    return ConversationSQLAlchemyRepository(db)


def get_prompt_repo(db: AsyncSession = Depends(get_db)) -> IPromptRepository:
    """
    Создаёт репозиторий промптов для работы с БД.

    Args:
        db: Асинхронная сессия БД

    Returns:
        IPromptRepository: Репозиторий для CRUD операций с промптами
    """
    return PromptSQLAlchemyRepository(db)


def get_message_repo(db: AsyncSession = Depends(get_db)) -> IMessageRepository:
    """
    Создаёт репозиторий сообщений для работы с БД.

    Args:
        db: Асинхронная сессия БД

    Returns:
        IMessageRepository: Репозиторий для CRUD операций с сообщениями
    """
    return MessageSQLAlchemyRepository(db)


def get_fact_repo(db: AsyncSession = Depends(get_db)) -> IFactRepository:
    """
    Создаёт репозиторий фактов с SQLAlchemy реализацией.

    Args:
        db: Асинхронная сессия БД

    Returns:
        IFactRepository: Репозиторий для CRUD операций с фактами
    """
    return FactsSQLAlchemyRepository(db)


def get_vacancy_repo(db: AsyncSession = Depends(get_db)) -> IVacancyRepository:
    return VacancySQLAlchemyRepository(db)


def get_vacancy_service(repo: IVacancyRepository = Depends(get_vacancy_repo)) -> VacancyService:
    """Фабрика сервиса вакансий."""
    return VacancyService(repo)


async def get_vacancy_archive_sync(
    vacancy_repo: IVacancyRepository = Depends(get_vacancy_repo),
    hh_client: AsyncClient = Depends(get_hh_client),
) -> VacancyArchiveSync:
    """Фабрика сервиса синхронизации архивных статусов вакансий."""
    return VacancyArchiveSync(vacancy_repo=vacancy_repo, hh_client=hh_client)


def get_user_service(repo: IUserRepository = Depends(get_user_repo)) -> UserService:
    """
    Создаёт сервис пользователей для бизнес-логики работы с пользователями.

    Args:
        repo: Репозиторий пользователей для доступа к данным

    Returns:
        UserService: Сервис с бизнес-логикой пользователей (регистрация, профиль)
    """
    return UserService(repo)


def get_auth_service(
    user_repo: IUserRepository = Depends(get_user_repo), invite_repo: IInviteRepository = Depends(get_invite_repo)
) -> AuthService:
    """
    Создаёт сервис авторизации для бизнес-логики аутентификации.

    Args:
        user_repo: Репозиторий пользователей для доступа к данным
        invite_repo: Репозиторий приглашений для регистрации по инвайту

    Returns:
        AuthService: Сервис с бизнес-логикой авторизации (логин, регистрация, токены)
    """
    return AuthService(user_repo, invite_repo, require_invite=settings.REQUIRE_INVITE)


def get_invite_service(invite_repo: IInviteRepository = Depends(get_invite_repo)) -> InviteService:
    """
    Создаёт сервис приглашений для бизнес-логики работы с инвайтами.

    Args:
        invite_repo: Репозиторий приглашений для доступа к данным

    Returns:
        InviteService: Сервис с бизнес-логикой приглашений (генерация, валидация, использование)
    """
    return InviteService(invite_repo)


def get_document_service(document_repo: IDocumentRepository = Depends(get_document_repo)) -> DocumentService:
    """
    Создаёт сервис документов для бизнес-логики работы с документами.

    Args:
        document_repo: Репозиторий документов для доступа к данным

    Returns:
        DocumentService: Сервис с бизнес-логикой документов (создание, поиск, обновление)
    """
    return DocumentService(document_repo)


def get_conversation_service(
    conversation_repo: IConversationRepository = Depends(get_conversation_repo),
) -> ConversationService:
    """
    Создаёт сервис бесед для бизнес-логики работы с беседами.

    Args:
        conversation_repo: Репозиторий бесед для доступа к данным

    Returns:
        ConversationService: Сервис с бизнес-логикой бесед (создание, обновление, удаление)
    """
    return ConversationService(conversation_repo)


def get_prompt_service(prompt_repo: IPromptRepository = Depends(get_prompt_repo)) -> PromptService:
    """
    Создаёт сервис промптов для бизнес-логики работы с промптами.

    Args:
        prompt_repo: Репозиторий промптов для доступа к данным

    Returns:
        PromptService: Сервис с бизнес-логикой промптов
    """
    return PromptService(prompt_repo)


def get_memory_service(
    memory: AsyncMemory = Depends(get_memory),
) -> IMemoryService:
    """
    Создаёт сервис памяти для работы с mem0ai.

    Args:
        memory: Асинхронный клиент mem0ai

    Returns:
        IMemoryService: Сервис для управления долгосрочной памятью пользователя
    """
    return create_memory_service(memory)


def get_llm_service() -> ILLMService:
    """
    Создаёт LLM сервис для генерации ответов.

    Returns:
        ILLMService: Сервис для работы с языковыми моделями
    """
    return create_llm_service(base_config_for_llm)


def get_message_service(
    message_repo: IMessageRepository = Depends(get_message_repo),
    conversation_repo: IConversationRepository = Depends(get_conversation_repo),
    prompt_repo: IPromptRepository = Depends(get_prompt_repo),
    llm_service: ILLMService = Depends(get_llm_service),
    memory_service: IMemoryService = Depends(get_memory_service),
) -> MessageService:
    """
    Создаёт сервис сообщений для бизнес-логики работы с сообщениями.

    Args:
        message_repo: Репозиторий сообщений для доступа к данным
        conversation_repo: Репозиторий бесед для доступа к данным
        prompt_repo: Репозиторий промптов для доступа к данным
        llm_service: Сервис LLM для генерации ответов
        memory_service: Сервис памяти для интеграции с mem0ai

    Returns:
        MessageService: Сервис с бизнес-логикой сообщений
    """
    return MessageService(
        message_repo=message_repo,
        conversation_repo=conversation_repo,
        prompt_repo=prompt_repo,
        llm_service=llm_service,
        memory_service=memory_service,
    )


def get_fact_service(
    fact_repo: IFactRepository = Depends(get_fact_repo),
    message_repo: IMessageRepository = Depends(get_message_repo),
    memory_service: IMemoryService = Depends(get_memory_service),
) -> FactService:
    """
    Создаёт сервис фактов для бизнес-логики работы с фактами.

    Args:
        fact_repo: Репозиторий фактов для доступа к данным
        message_repo: Репозиторий сообщений для импорта фактов
        memory_service: Сервис памяти для интеграции с mem0ai

    Returns:
        FactService: Сервис с бизнес-логикой фактов (CRUD, импорт из mem0ai)
    """
    return FactService(
        fact_repo=fact_repo,
        message_repo=message_repo,
        memory_service=memory_service,
    )


def get_upload_service(
    conversation_repo: IConversationRepository = Depends(get_conversation_repo),
    message_repo: IMessageRepository = Depends(get_message_repo),
) -> UploadService:
    """ """
    return UploadService(conversation_repo, message_repo)


def get_researcher_llm() -> AsyncOpenAILLM:
    """FastAPI зависимость для AI-исследования."""
    return create_analysis_llm()


def get_vacancy_analyzer(
    llm: AsyncOpenAILLM = Depends(get_researcher_llm),
    vacancy_repo: IVacancyRepository = Depends(get_vacancy_repo),
) -> VacancyAnalyzer:
    return VacancyAnalyzer(llm, vacancy_repo)


async def get_current_user(
    request: Request, token: str = Depends(oauth2_scheme), user_repo: IUserRepository = Depends(get_user_repo)
) -> UserModel:
    """
    Аутентифицирует пользователя через JWT токен и возвращает модель пользователя.

    Декодирует JWT, извлекает username и загружает пользователя из БД.
    Логирует неудачные попытки с IP и endpoint для мониторинга безопасности.

    Args:
        request: FastAPI Request объект для логирования (IP, endpoint)
        token: JWT access токен из Authorization header
        user_repo: Репозиторий пользователей для поиска в БД

    Returns:
        UserModel: Модель авторизованного пользователя

    Raises:
        HTTPException 401: Невалидный/истёкший токен или пользователь не найден
    """
    client_ip = request.client.host if request.client else "unknown"
    endpoint = request.url.path
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload: TokenPayload = decode_token(token)
        username: str = payload.sub
        if username is None:
            logger.warning("JWT без sub | ip={} endpoint={}", client_ip, endpoint)
            raise credentials_exception from None

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired", headers={"WWW-Authenticate": "Bearer"}
        ) from None

    except jwt.PyJWTError:
        logger.warning("Невалидный JWT | ip={} endpoint={}", client_ip, endpoint)
        raise credentials_exception from None

    user = await user_repo.get_by_username(username)
    if user is None:
        logger.warning("Пользователь не найден | ip={} endpoint={}", client_ip, endpoint)
        raise credentials_exception from None
    return user


async def get_current_admin_user(current_user: UserModel = Depends(get_current_user)) -> UserModel:
    """
    Проверяет наличие прав администратора у текущего пользователя.

    Защищает эндпоинты, доступные только пользователям с ролью ADMIN.
    Логирует попытки несанкционированного доступа для мониторинга безопасности.

    Args:
        current_user: Модель текущего авторизованного пользователя

    Returns:
        UserModel: Модель пользователя с ролью администратора

    Raises:
        HTTPException 403: Пользователь не имеет роль ADMIN
    """
    if current_user.role != UserRole.ADMIN:
        logger.warning("Попытка доступа без прав админа | user_id={}", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        ) from None
    return current_user
