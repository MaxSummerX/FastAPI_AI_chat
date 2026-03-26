from datetime import UTC, datetime
from uuid import UUID

import jwt
from loguru import logger

from app.application.exceptions.auth import (
    InvalidCredentialsException,
    InvalidInviteCodeException,
    InvalidTokenException,
    TokenExpiredException,
    UserAlreadyExistsException,
    WrongTokenTypeException,
)
from app.application.schemas.auth import RefreshTokenResponse, TokenResponse
from app.application.schemas.user import UserResponseBase
from app.domain.repositories.invites import IInviteRepository
from app.domain.repositories.users import IUserRepository
from app.infrastructure.security import hash_password, verify_password
from app.infrastructure.security.jwt_service import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    create_refresh_token,
    decode_token,
)


class AuthService:
    """Сервис для аутентификации и регистрации пользователей"""

    def __init__(self, user_repo: IUserRepository, invite_repo: IInviteRepository, require_invite: bool = False):
        self.user_repo = user_repo
        self.invite_repo = invite_repo
        self.require_invite = require_invite

    async def register_user(
        self,
        username: str,
        email: str,
        password: str,
        invite_code: str | None = None,
    ) -> UserResponseBase:
        """
        Единая точка регистрации для роутера.

        Делегирует выполнение нужному методу в зависимости от настроек REQUIRE_INVITE.

        Args:
            username: Имя пользователя
            email: Email пользователя
            password: Пароль (plaintext)
            invite_code: Опциональный инвайт-код (обязателен если REQUIRE_INVITE=True)

        Returns:
            UserResponseBase с данными созданного пользователя

        Raises:
            InvalidInviteCodeException: Если REQUIRE_INVITE=True но код не передан
        """
        if self.require_invite:
            if not invite_code:
                logger.warning("Попытка регистрации без инвайт-кода | email={}", email)
                raise InvalidInviteCodeException("Invite code is required")
            return await self.register_with_invite(invite_code, username, email, password)

        return await self.register(username, email, password)

    async def register(self, username: str, email: str, password: str) -> UserResponseBase:
        """
        Регистрирует нового пользователя.

        Args:
            username: Имя пользователя
            email: Email пользователя
            password: Пароль (plaintext)

        Returns:
            UserResponseBase с данными созданного пользователя

        Raises:
            UserAlreadyExistsException: Если username или email уже заняты
        """
        if not await self.user_repo.is_username_unique(username):
            logger.warning("Попытка регистрации с занятым username: {}", username)
            raise UserAlreadyExistsException("Username already exists")

        if not await self.user_repo.is_email_unique(email):
            logger.warning("Попытка регистрации с занятым email: {}", email)
            raise UserAlreadyExistsException("Email already exists")

        hashed_password = hash_password(password)

        new_user = await self.user_repo.create(username=username, email=email, password_hash=hashed_password)

        return UserResponseBase.model_validate(new_user)

    async def register_with_invite(
        self, invite_code: str, username: str, email: str, password: str
    ) -> UserResponseBase:
        """
        Регистрирует нового пользователя с инвайт-кодом.

        Args:
            invite_code: Инвайт-код
            username: Имя пользователя
            email: Email пользователя
            password: Пароль (plaintext)

        Returns:
            UserResponseBase с данными созданного пользователя

        Raises:
            InvalidInviteCodeException: Если код неверный или уже использован
            UserAlreadyExistsException: Если username или email уже заняты
        """
        invite = await self.invite_repo.get_available_invite(invite_code)

        if not invite:
            logger.warning("Попытка регистрации с неверным invite кодом | email={}", email)
            raise InvalidInviteCodeException("Invalid or used invitation code")

        if not await self.user_repo.is_username_unique(username):
            logger.warning("Попытка регистрации с занятым username: {}", username)
            raise UserAlreadyExistsException("Username already exists")

        if not await self.user_repo.is_email_unique(email):
            logger.warning("Попытка регистрации с занятым email: {}", email)
            raise UserAlreadyExistsException("Email already exists")

        hashed_password = hash_password(password)

        new_user = await self.user_repo.create(username=username, email=email, password_hash=hashed_password)

        await self.invite_repo.mark_as_used(invite, new_user.id)

        return UserResponseBase.model_validate(new_user)

    async def login(self, username_or_email: str, password: str) -> tuple[UUID, TokenResponse]:
        """
        Аутентифицирует пользователя и возвращает токены.

        Args:
            username_or_email: Username или email пользователя
            password: Пароль (plaintext)

        Returns:
            TokenResponse с access и refresh токенами

        Raises:
            InvalidCredentialsException: Если неверный username/email или пароль
        """

        # Ищем пользователя по username или email
        user = await self.user_repo.get_by_email_or_username(username_or_email)

        if not user:
            logger.warning("Попытка входа с несуществующим username: {}", username_or_email)
            raise InvalidCredentialsException("Incorrect username or password")

        # Проверяем пароль
        if not verify_password(password, user.password_hash):
            logger.warning("Неверный пароль для username: {}", username_or_email)
            raise InvalidCredentialsException("Incorrect username or password")

        # Обновляем время последнего входа
        user.last_login = datetime.now(UTC)
        await self.user_repo.save(user)

        # Создаём токены
        access_token = create_access_token(
            username=user.username, user_id=str(user.id), email=user.email, role=user.role.value
        )

        refresh_token = create_refresh_token(
            username=user.username, user_id=str(user.id), email=user.email, role=user.role.value
        )

        return user.id, TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def refresh_token(self, refresh_token: str) -> RefreshTokenResponse:
        """
        Обновляет access токен с помощью refresh токена.

        Args:
            refresh_token: Refresh токен (raw JWT string)

        Returns:
            RefreshTokenResponse с новым access токеном

        Raises:
            TokenExpiredException: Если токен истёк
            InvalidTokenException: Если токен невалиден или юзер не найден
            WrongTokenTypeException: Если передан access токен вместо refresh
        """
        try:
            payload = decode_token(refresh_token)

        except jwt.ExpiredSignatureError:
            raise TokenExpiredException("Refresh token has expired") from None

        except jwt.PyJWTError:
            logger.warning("Невалидный JWT при обновлении токена")
            raise InvalidTokenException("Invalid refresh token") from None

        # Проверяем, что это именно refresh токен (у refresh есть jti)
        if payload.jti is None:
            logger.warning("Передан access токен вместо refresh | username={}", payload.sub)
            raise WrongTokenTypeException("Expected refresh token, got access token") from None

        user = await self.user_repo.get_by_username(payload.sub)
        if not user:
            logger.warning("Юзер не найден при обновлении токена | username={}", payload.sub)
            raise InvalidTokenException("Invalid refresh token") from None

        access_token = create_access_token(
            username=user.username, user_id=str(user.id), email=user.email, role=user.role.value
        )

        return RefreshTokenResponse(
            access_token=access_token, token_type="bearer", expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
