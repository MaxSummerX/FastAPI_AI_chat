from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from loguru import logger

from app.application.exceptions.auth import (
    InvalidCredentialsException,
    InvalidInviteCodeException,
    InvalidTokenException,
    TokenExpiredException,
    UserAlreadyExistsException,
    WrongTokenTypeException,
)
from app.application.exceptions.user import (
    EmailAlreadyExistsException,
    IncorrectPasswordException,
    SameEmailException,
    SamePasswordException,
    SameUsernameException,
    UsernameAlreadyExistsException,
)
from app.application.schemas.auth import RefreshTokenResponse, TokenResponse
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
from app.presentation.dependencies import get_auth_service, get_current_user, get_user_service


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
    try:
        return await service.get_full_profile(current_user.id)

    except Exception as e:
        logger.error("Ошибка при получении полной информации пользователя {}: {}", current_user.id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving user information",
        ) from None


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
    logger.info("Попытка регистрации: username={}, email={}{})", user.username, user.email, invite_info)

    try:
        new_user = await auth_service.register_user(
            username=user.username,
            email=str(user.email),
            password=user.password,
            invite_code=user.invite_code,
        )
        logger.info("Пользователь успешно зарегистрирован: {}", new_user.id)
        return new_user

    except InvalidInviteCodeException as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from None

    except UserAlreadyExistsException as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from None

    except Exception as e:
        logger.error("Непредвиденная ошибка при регистрации: {}", e)
        raise HTTPException(status_code=500, detail="Internal server error") from None


@router.post("/token", summary="Получить JWT токены (логин)")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(), auth_service: AuthService = Depends(get_auth_service)
) -> TokenResponse:
    """
    Аутентифицирует пользователя по username или паролю и возвращает JWT токены.

    **Возможные ошибки:**
    - `401` — неверный username или пароль
    """
    logger.info("Попытка входа: username={}", form_data.username)

    try:
        user_id, access_token = await auth_service.login(form_data.username, form_data.password)
        logger.info("Пользователь успешно вошёл: {}", user_id)
        return access_token

    except InvalidCredentialsException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    except Exception as e:
        logger.error("Error при входе пользователя {}: {}", form_data.username, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error during login",
        ) from None


@router.post("/refresh-token", summary="Обновить access токен")
async def get_refresh_token(
    refresh_token: str, auth_service: AuthService = Depends(get_auth_service)
) -> RefreshTokenResponse:
    """
    Обновляет access токен с помощью refresh токена.

    **Возможные ошибки:**
    - `401` — неверный, истёкший или неправильный тип токена
    """
    try:
        return await auth_service.refresh_token(refresh_token)

    except (InvalidTokenException, TokenExpiredException, WrongTokenTypeException) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    except Exception as e:
        logger.error("Ошибка обновления токена: {}", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error refreshing token",
        ) from None


@router.patch("/update", status_code=status.HTTP_200_OK, summary="Обновить профиль")
async def update_user_profile(
    user_data: UserUpdateProfile,
    current_user: UserModel = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> UserResponseFull:
    """Обновляет дополнительные данные профиля текущего пользователя."""
    try:
        update_user = await user_service.update_user_profile(current_user.id, user_data)
        return update_user

    except Exception as e:
        logger.error("Ошибка при обновлении профиля: {}", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating profile",
        ) from None


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

    try:
        update_user = await user_service.update_email(
            current_user.id, str(email_data.new_email), email_data.current_password
        )
        logger.info("Email пользователя успешно обновлён: {}", current_user.id)
        return update_user

    except EmailAlreadyExistsException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None

    except IncorrectPasswordException as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from None

    except SameEmailException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None

    except Exception as e:
        logger.error("Ошибка при обновлении email: {}", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating email",
        ) from None


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

    try:
        update_user = await user_service.change_password(
            current_user.id, password_data.current_password, password_data.password
        )
        logger.info("Пароль пользователя успешно обновлён: {}", current_user.id)
        return update_user

    except IncorrectPasswordException as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from None

    except SamePasswordException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None

    except Exception as e:
        logger.error("Неожиданная ошибка при обновлении пароля {}: {}", current_user.id, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from None


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

    try:
        username_update = await user_service.update_username(
            current_user.id, username_data.username, username_data.current_password
        )
        logger.info("Username пользователя успешно обновлён: {}", current_user.id)
        return username_update

    except IncorrectPasswordException as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from None

    except UsernameAlreadyExistsException as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None

    except SameUsernameException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None

    except Exception as e:
        logger.error("Неожиданная ошибка при обновлении username {}: {}", current_user.id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error updating username"
        ) from None
