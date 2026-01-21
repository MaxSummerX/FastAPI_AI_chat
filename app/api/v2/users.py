from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from loguru import logger
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.auth import create_access_token, create_refresh_token, hash_password, verify_password
from app.auth.dependencies import get_current_user
from app.auth.jwt_config import ALGORITHM, SECRET_KEY
from app.auth.tokens import ACCESS_TOKEN_EXPIRE_MINUTES
from app.depends.db_depends import get_async_postgres_db
from app.models.invites import Invite as InviteModel
from app.models.users import User as UserModel
from app.schemas.users import (
    UserRegister,
    UserUpdateEmail,
    UserUpdatePassword,
    UserUpdateProfile,
    UserUpdateUsername,
)
from app.schemas.users import UserResponseBase as UserBaseSchema
from app.schemas.users import UserResponseFull as UserFullSchema
from app.utils.user_validators import validate_user_unique


router = APIRouter(prefix="/user", tags=["User_V2"])


@router.get("/", status_code=status.HTTP_200_OK, summary="Получить базовую информацию о пользователе")
async def get_base_user_info(current_user: UserModel = Depends(get_current_user)) -> UserBaseSchema:
    """
    Возвращает основную информацию о пользователе
    """
    logger.info(f"Запрос базовой информации пользователя: {current_user.id}")
    return UserBaseSchema.model_validate(current_user)


@router.get("/info", status_code=status.HTTP_200_OK, summary="Получить полную информацию о пользователе")
async def get_full_user_info(
    current_user: UserModel = Depends(get_current_user), db: AsyncSession = Depends(get_async_postgres_db)
) -> UserFullSchema:
    """
    Возвращает полную информацию о текущем пользователе.
    """
    logger.info(f"Запрос полной информации пользователя: {current_user.id}")
    try:
        result = await db.scalars(
            select(UserModel).where(UserModel.email == current_user.email, UserModel.is_active.is_(True))
        )
        user = result.first()
        return UserFullSchema.model_validate(user)

    except Exception as e:
        logger.error(f"Ошибка при получении полной информации пользователя {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving user information",
        ) from e


@router.post("/register", status_code=status.HTTP_201_CREATED, summary="Зарегистрировать нового пользователя")
async def register_user(user: UserRegister, db: AsyncSession = Depends(get_async_postgres_db)) -> UserBaseSchema:
    """
    Регистрирует нового пользователя в системе.
    """
    logger.info(f"Попытка регистрации пользователя: username={user.username}, email={user.email}")
    try:
        # Проверяем уникальность username и email
        await validate_user_unique(db, user.username, user.email)

        # Хэшируем пароль
        hashed_password = hash_password(user.password)
        # Создание объекта пользователя с хешированием пароля
        new_user = UserModel(username=user.username, email=user.email, password_hash=hashed_password)

        # Добавляем в сессию и сохранение в базе
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        logger.info(f"Пользователь успешно зарегистрирован: {new_user.id}")

        return UserBaseSchema.model_validate(new_user)

    except HTTPException:
        # Пробрасываем HTTPException
        raise

    except IntegrityError as e:
        # Дополнительная защита от race conditions
        await db.rollback()
        logger.error(f"IntegrityError при регистрации: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already exists",
        ) from e

    except SQLAlchemyError as e:
        # Общая ошибка БД
        await db.rollback()
        logger.error(f"Database error при регистрации пользователя {user.username}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating user account",
        ) from e

    except Exception as e:
        # Неожиданная ошибка
        await db.rollback()
        logger.error(f"Unexpected error при регистрации пользователя {user.username}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred",
        ) from e


@router.post("/register_with_invite", status_code=status.HTTP_201_CREATED, summary="Зарегистрироваться с инвайт-кодом")
async def register_with_invite(
    invite_code: str,
    user: UserRegister,
    db: AsyncSession = Depends(get_async_postgres_db),
) -> UserBaseSchema:
    """
    Регистрирует нового пользователя с использованием invite кода.
    """
    logger.info(f"Попытка регистрации с invite кодом: code={invite_code}, email={user.email}")

    try:
        # Проверяем валидность invite кода
        invite = await db.scalars(
            select(InviteModel).where(InviteModel.code == invite_code, InviteModel.is_used.is_(False))
        )
        invite = invite.first()

        if not invite:
            logger.warning(f"Попытка регистрации с неверным invite кодом: {invite_code}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or used invitation code",
            )

        # Проверяем уникальность username и email
        await validate_user_unique(db, user.username, user.email)

        # Хешируем пароль
        hashed_password = hash_password(user.password)

        # Создание объекта пользователя с хешированием пароля
        new_user = UserModel(username=user.username, email=user.email, password_hash=hashed_password)

        # Добавляем в сессию
        db.add(new_user)
        await db.flush()  # Получаем ID пользователя без коммита

        # Помечаем invite как использованный
        invite.is_used = True
        invite.used_by_user_id = new_user.id
        invite.used_at = datetime.now(UTC)

        # Коммитим оба изменения
        await db.commit()
        await db.refresh(new_user)

        logger.info(f"Пользователь успешно зарегистрирован с invite кодом: {new_user.id}")

        return UserBaseSchema.model_validate(new_user)

    except HTTPException:
        # Пробрасываем HTTPException
        raise

    except IntegrityError as e:
        await db.rollback()
        logger.error(f"IntegrityError при регистрации с invite: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already exists",
        ) from e

    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Database error при регистрации с invite {invite_code}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating user account",
        ) from e

    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error при регистрации с invite {invite_code}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred",
        ) from e


@router.post("/token", summary="Получить JWT токены (логин)")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> dict:
    """
    Аутентифицирует пользователя и возвращает JWT токены.
    """
    logger.info(f"Попытка входа: username={form_data.username}")

    try:
        # Ищем пользователя по username или email
        result = await db.scalars(
            select(UserModel).where(
                or_(UserModel.username == form_data.username, UserModel.email == form_data.username),
                UserModel.is_active,
            )
        )

        user = result.first()

        # Проверяем пароль
        if not user or not verify_password(form_data.password, user.password_hash):
            logger.warning(f"Неудачная попытка входа: username={form_data.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Обновляем время последнего входа
        user.last_login = datetime.now(UTC)
        await db.commit()

        # Создаём токены
        access_token = create_access_token(data={"sub": user.username, "id": user.id, "email": user.email})
        refresh_token = create_refresh_token(data={"sub": user.username, "id": user.id, "email": user.email})

        logger.info(f"Пользователь успешно вошёл: {user.id}")

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # в секундах
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error при входе пользователя {form_data.username}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error during login",
        ) from e


@router.post("/refresh-token", summary="Обновить access токен")
async def get_refresh_token(
    refresh_token: str,
    db: AsyncSession = Depends(get_async_postgres_db),
) -> dict:
    """
    Обновляет access токен с помощью refresh токена.
    """
    logger.info("Попытка обновления токена")

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Декодируем refresh токен
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")

        if username is None:
            logger.warning("Refresh токен не содержит username")
            raise credentials_exception

    except jwt.PyJWTError as e:
        logger.warning(f"Ошибка декодирования refresh токена: {e}")
        raise credentials_exception from None

    try:
        # Проверяем, что пользователь существует и активен
        result = await db.scalars(
            select(UserModel).where(UserModel.username == username, UserModel.is_active.is_(True))
        )
        user = result.first()

        if user is None:
            logger.warning(f"Пользователь из refresh токена не найден: {username}")
            raise credentials_exception

        # Создаём новый access токен
        access_token = create_access_token(data={"sub": user.username, "id": user.id, "email": user.email})

        logger.info(f"Токен успешно обновлён для пользователя: {user.id}")

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error при обновлении токена: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error refreshing token",
        ) from e


@router.patch("/update", status_code=status.HTTP_200_OK, summary="Обновить профиль")
async def update_user_profile(
    user_info: UserUpdateProfile,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> UserFullSchema:
    """
    Обновляет профиль пользователя.
    """
    logger.info(f"Попытка обновления профиля пользователя: {current_user.id}")

    try:
        # Формируем словарь с обновлениями (только не-None поля)
        update_data = user_info.model_dump(exclude_unset=True, by_alias=False)

        if not update_data:
            # Нет данных для обновления
            return UserFullSchema.model_validate(current_user)

        # Выполняем обновление
        result = await db.execute(select(UserModel).where(UserModel.id == current_user.id).with_for_update())
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Применяем обновления
        for field, value in update_data.items():
            setattr(user, field, value)

        await db.commit()
        await db.refresh(user)

        logger.info(f"Профиль пользователя успешно обновлён: {user.id}")

        return UserFullSchema.model_validate(user)

    except HTTPException:
        raise

    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Database error при обновлении профиля {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating user profile",
        ) from e

    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error при обновлении профиля {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred",
        ) from e


@router.post("/update-email", status_code=status.HTTP_200_OK, summary="Обновить email")
async def update_user_email(
    data: UserUpdateEmail,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> UserBaseSchema:
    """
    Обновляет email пользователя.
    Требуется текущий пароль для подтверждения.
    """
    logger.info(f"Попытка обновления email пользователя: {current_user.id}")

    try:
        # 1. Проверяем текущий пароль
        if not verify_password(data.current_password, current_user.password_hash):
            logger.warning(f"Неверный пароль при попытке обновления email: {current_user.id}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный текущий пароль")

        # 2. Проверяем что новый email отличается от текущего
        if data.new_email == current_user.email:
            logger.info(f"Новый email совпадает с текущим: {current_user.id}")
            return UserBaseSchema.model_validate(current_user)

        # 3. Проверяем что новый email уникален
        await validate_user_unique(db, current_user.username, data.new_email, exclude_user_id=current_user.id)

        # 4. Обновляем email
        result = await db.execute(
            update(UserModel).where(UserModel.id == current_user.id).values(email=data.new_email).returning(UserModel)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

        await db.commit()
        logger.info(f"Email пользователя успешно обновлён: {user.id}")

        return UserBaseSchema.model_validate(user)

    except HTTPException:
        raise

    except IntegrityError as e:
        await db.rollback()
        error_detail = str(e.orig).lower()

        if "email" in error_detail or "users_email_key" in error_detail:
            logger.warning(f"Попытка обновить email на уже занятый: {current_user.id}")
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email уже зарегистрирован") from e

        logger.error(f"IntegrityError при обновлении email: {current_user.id}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нарушение ограничений уникальности") from e

    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Ошибка базы данных при обновлении email {current_user.id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка базы данных") from e

    except Exception as e:
        await db.rollback()
        logger.error(f"Неожиданная ошибка при обновлении email {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера"
        ) from e


@router.post("/update-password", status_code=status.HTTP_200_OK, summary="Обновить пароль")
async def update_user_password(
    data: UserUpdatePassword,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> UserBaseSchema:
    """
    Обновляет пароль пользователя.
    Требуется текущий пароль для подтверждения.
    """
    logger.info(f"Попытка обновления пароля пользователя: {current_user.id}")

    try:
        # 1. Проверяем текущий пароль
        if not verify_password(data.current_password, current_user.password_hash):
            logger.warning(f"Неверный пароль при попытке обновления пароля: {current_user.id}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный текущий пароль")

        # 2. Проверяем что новый пароль отличается от текущего
        if verify_password(data.password, current_user.password_hash):
            logger.info(f"Новый пароль совпадает с текущим: {current_user.id}")
            return UserBaseSchema.model_validate(current_user)

        # 3. Хешируем новый пароль
        new_password_hash = hash_password(data.password)

        # 4. Обновляем пароль
        result = await db.execute(
            update(UserModel)
            .where(UserModel.id == current_user.id)
            .values(password_hash=new_password_hash)
            .returning(UserModel)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

        await db.commit()
        logger.info(f"Пароль пользователя успешно обновлён: {user.id}")

        return UserBaseSchema.model_validate(user)

    except HTTPException:
        raise

    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Ошибка базы данных при обновлении пароля {current_user.id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка базы данных") from e

    except Exception as e:
        await db.rollback()
        logger.error(f"Неожиданная ошибка при обновлении пароля {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера"
        ) from e


@router.post("/update-username", status_code=status.HTTP_200_OK, summary="Обновить username")
async def update_user_username(
    data: UserUpdateUsername,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> UserBaseSchema:
    """
    Обновляет username пользователя.
    Требуется текущий пароль для подтверждения.
    """
    logger.info(f"Попытка обновления username пользователя: {current_user.id}")

    try:
        # 1. Проверяем текущий пароль
        if not verify_password(data.current_password, current_user.password_hash):
            logger.warning(f"Неверный пароль при попытке обновления username: {current_user.id}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный текущий пароль")

        # 2. Проверяем что новый username отличается от текущего
        if data.username == current_user.username:
            logger.info(f"Новый username совпадает с текущим: {current_user.id}")
            return UserBaseSchema.model_validate(current_user)

        # 3. Проверяем что новый username уникален
        await validate_user_unique(db, data.username, current_user.email, exclude_user_id=current_user.id)

        # 4. Обновляем username
        result = await db.execute(
            update(UserModel).where(UserModel.id == current_user.id).values(username=data.username).returning(UserModel)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Пользователь не найден")

        await db.commit()
        logger.info(f"Username пользователя успешно обновлён: {user.id}")

        return UserBaseSchema.model_validate(user)

    except HTTPException:
        raise

    except IntegrityError as e:
        await db.rollback()
        error_detail = str(e.orig).lower()

        if "username" in error_detail or "users_username_key" in error_detail:
            logger.warning(f"Попытка обновить username на уже занятый: {current_user.id}")
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username уже занят") from e

        logger.error(f"IntegrityError при обновлении username: {current_user.id}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Нарушение ограничений уникальности") from e

    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Ошибка базы данных при обновлении username {current_user.id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Ошибка базы данных") from e

    except Exception as e:
        await db.rollback()
        logger.error(f"Неожиданная ошибка при обновлении username {current_user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Внутренняя ошибка сервера"
        ) from e
