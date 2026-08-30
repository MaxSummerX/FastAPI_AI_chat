from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from loguru import logger

from app.application.schemas.auth import MessageResponse, RefreshTokenResponse, TokenResponse
from app.application.schemas.user import (
    UserRegister,
    UserResponseBase,
    UserResponseFull,
    UserUpdateEmail,
    UserUpdatePassword,
    UserUpdateProfile,
    UserUpdateUsername,
)
from app.application.services.auth_service import AuthService
from app.application.services.user_service import UserService
from app.domain.models.user import User as UserModel
from app.infrastructure.security.jwt_service import ACCESS_TOKEN_EXPIRE_MINUTES
from app.presentation.dependencies import get_auth_service, get_current_user, get_user_service
from app.presentation.security.cookies import REFRESH_COOKIE_NAME, clear_refresh_cookie, set_refresh_cookie


router = APIRouter(prefix="/user", tags=["User"])


@router.get("", status_code=status.HTTP_200_OK, summary="Получить базовую информацию о пользователе")
async def get_base_user_info(current_user: UserModel = Depends(get_current_user)) -> UserResponseBase:
    """Возвращает базовую информацию о текущем авторизованном пользователе."""
    return UserResponseBase.model_validate(current_user)


@router.get("/info", status_code=status.HTTP_200_OK, summary="Получить полную информацию о пользователе")
async def get_full_user_info(
    current_user: UserModel = Depends(get_current_user), service: UserService = Depends(get_user_service)
) -> UserResponseFull:
    """Возвращает расширенную информацию о текущем авторизованном пользователе."""
    return await service.get_full_profile(current_user.id)


@router.post("/register", status_code=status.HTTP_201_CREATED, summary="Зарегистрировать нового пользователя")
async def register_user(
    user: UserRegister,
    auth_service: AuthService = Depends(get_auth_service),
) -> UserResponseBase:
    """
    Регистрирует нового пользователя в системе.

    Если включена настройка REQUIRE_INVITE, необходимо передать валидный инвайт-код.

    **Возможные ошибки:**
    - `403` — неверный или уже использованный инвайт-код
    - `409` — username или email уже заняты
    """
    invite_info = f" invite={user.invite_code[:4]}..." if user.invite_code else ""
    logger.info("Попытка регистрации: username={}, email={}{}", user.username, user.email, invite_info)

    new_user = await auth_service.register_user(
        username=user.username,
        email=str(user.email),
        password=user.password,
        invite_code=user.invite_code,
    )
    logger.info("Пользователь успешно зарегистрирован: {}", new_user.id)
    return new_user


@router.post("/token", summary="Получить JWT токены (логин)")
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """
    Аутентифицирует пользователя по username или паролю.

    Access токен возвращается в теле ответа, refresh — в httpOnly cookie.

    **Возможные ошибки:**
    - `401` — неверный username или пароль
    """
    logger.info("Попытка входа: username={}", form_data.username)

    user_id, access_token, refresh_token = await auth_service.login(form_data.username, form_data.password)
    logger.info("Пользователь успешно вошёл: {}", user_id)
    set_refresh_cookie(response, refresh_token)
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",  # nosec B106
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh-token", summary="Обновить access токен")
async def get_refresh_token(
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
    auth_service: AuthService = Depends(get_auth_service),
) -> RefreshTokenResponse:
    """
    Обновляет access токен с помощью refresh токена.

    **Возможные ошибки:**
    - `401` — неверный, истёкший или неправильный тип токена
    """
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token cookie is missing")
    return await auth_service.refresh_token(refresh_token)


@router.post("/logout", summary="Выйти")
async def logout(response: Response) -> MessageResponse:
    """Завершает сессию: удаляет refresh cookie."""
    clear_refresh_cookie(response)
    return MessageResponse(detail="Logged out")


@router.patch("/update", status_code=status.HTTP_200_OK, summary="Обновить профиль")
async def update_user_profile(
    user_data: UserUpdateProfile,
    current_user: UserModel = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> UserResponseFull:
    """Обновляет дополнительные данные профиля текущего пользователя."""
    update_user = await user_service.update_user_profile(current_user.id, user_data)
    return update_user


@router.post("/email", status_code=status.HTTP_200_OK, summary="Обновить email")
async def update_user_email(
    email_data: UserUpdateEmail,
    current_user: UserModel = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> UserResponseBase:
    """
    Обновляет email текущего пользователя.

    Требует подтверждения текущим паролем.

    **Возможные ошибки:**
    - `400` — новый email совпадает с текущим
    - `401` — неверный текущий пароль
    - `409` — email уже занят другим пользователем
    """
    logger.info("Попытка обновления email пользователя: {}", current_user.id)

    update_user = await user_service.update_email(
        current_user.id, str(email_data.new_email), email_data.current_password
    )
    logger.info("Email пользователя успешно обновлён: {}", current_user.id)
    return update_user


@router.post("/password", status_code=status.HTTP_200_OK, summary="Обновить пароль")
async def update_user_password(
    password_data: UserUpdatePassword,
    current_user: UserModel = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> UserResponseBase:
    """
    Обновляет пароль текущего пользователя.

    Требует подтверждения текущим паролем.

    **Возможные ошибки:**
    - `400` — новый пароль совпадает с текущим
    - `401` — неверный текущий пароль
    """
    logger.info("Попытка обновления пароля пользователя: {}", current_user.id)

    update_user = await user_service.change_password(
        current_user.id, password_data.current_password, password_data.password
    )
    logger.info("Пароль пользователя успешно обновлён: {}", current_user.id)
    return update_user


@router.post("/username", status_code=status.HTTP_200_OK, summary="Обновить username")
async def update_user_username(
    username_data: UserUpdateUsername,
    current_user: UserModel = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> UserResponseBase:
    """
    Обновляет username текущего пользователя.

    Требует подтверждения текущим паролем.

    **Возможные ошибки:**
    - `400` — новый username совпадает с текущим
    - `401` — неверный текущий пароль
    - `409` — username уже занят другим пользователем
    """
    logger.info("Попытка обновления username пользователя: {}", current_user.id)

    username_update = await user_service.update_username(
        current_user.id, username_data.username, username_data.current_password
    )
    logger.info("Username пользователя успешно обновлён: {}", current_user.id)
    return username_update
