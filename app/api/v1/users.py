from datetime import UTC, datetime
from typing import cast

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from loguru import logger
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.auth import create_access_token, create_refresh_token, hash_password, verify_password
from app.auth.dependencies import get_current_user
from app.auth.jwt_config import ALGORITHM, SECRET_KEY
from app.depends.db_depends import get_async_postgres_db
from app.models.invites import Invite as InviteModel
from app.models.users import User as UserModel
from app.schemas.users import UserRegister, UserUpdateProfile
from app.schemas.users import UserResponseBase as UserBaseSchema
from app.schemas.users import UserResponseFull as UserFullSchema


router_v1 = APIRouter(prefix="/user", tags=["User"])


@router_v1.get("/", response_model=UserBaseSchema, status_code=status.HTTP_200_OK)
async def get_base_user_info(current_user: UserModel = Depends(get_current_user)) -> UserModel:
    """
    Возвращает основную информацию о пользователе
    """
    logger.info(f"Запрос базовой информации пользователя: {current_user.id}")
    return current_user


@router_v1.get("/info", response_model=UserFullSchema, status_code=status.HTTP_200_OK)
async def get_full_user_info(
    current_user: UserModel = Depends(get_current_user), db: AsyncSession = Depends(get_async_postgres_db)
) -> UserModel:
    """
    Возвращает полную информацию о пользователе
    """
    user = await db.scalars(
        select(UserModel).where(UserModel.email == current_user.email, UserModel.is_active.is_(True))
    )
    return cast(UserModel, user.first())


@router_v1.post("/register", response_model=UserBaseSchema, status_code=status.HTTP_201_CREATED)
async def register_user(user: UserRegister, db: AsyncSession = Depends(get_async_postgres_db)) -> UserModel:
    """
    Регистрирует нового пользователя.
    """
    # Проверяем уникальность username
    result_username = await db.scalars(select(UserModel).where(UserModel.username == user.username))
    if result_username.first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already registered")

    # Проверяем уникальность email
    result_email = await db.scalars(select(UserModel).where(UserModel.email == user.email))
    if result_email.first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    # Хэшируем пароль
    hashed_password = hash_password(user.password)
    # Создание объекта пользователя с хешированием пароля
    new_user = UserModel(username=user.username, email=user.email, password_hash=hashed_password)

    # Добавляем в сессию и сохранение в базе
    db.add(new_user)
    await db.commit()
    return new_user


@router_v1.post("/register_with_invite", response_model=UserBaseSchema, status_code=status.HTTP_201_CREATED)
async def register_with_invite(
    invite_code: str, user: UserRegister, db: AsyncSession = Depends(get_async_postgres_db)
) -> UserModel:
    """
    Регистрирует нового пользователя с использованием invite кода.
    """

    # Проверяем валидность invite кода
    invite = await db.scalars(
        select(InviteModel).where(InviteModel.code == invite_code, InviteModel.is_used.is_(False))
    )
    invite = invite.first()

    if not invite:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or used invitation code")

    # Проверяем уникальность username
    result_username = await db.scalars(select(UserModel).where(UserModel.username == user.username))
    if result_username.first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already registered")

    # Проверяем уникальность email
    result_email = await db.scalars(select(UserModel).where(UserModel.email == user.email))
    if result_email.first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    # Создание объекта пользователя с хешированием пароля
    user = UserModel(username=user.username, email=user.email, password_hash=hash_password(user.password))

    # Добавляем в сессию и сохранение в базе
    db.add(user)
    await db.flush()  # Получаем ID пользователя без коммита

    # Помечаем invite как использованный
    invite.is_used = True
    invite.used_by_user_id = user.id
    invite.used_at = datetime.now(UTC)

    await db.commit()

    logger.info(f"Invite {invite_code} used by user {user.email}")
    return user


@router_v1.post("/token")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_async_postgres_db)
) -> dict:
    """
    Аутентифицирует пользователя и возвращает JWT с email, id.
    """
    result = await db.scalars(
        select(UserModel).where(
            or_(UserModel.username == form_data.username, UserModel.email == form_data.username), UserModel.is_active
        )
    )

    user = cast(UserModel, result.first())

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Обновляем информацию о входе пользователя
    user.last_login = datetime.now(UTC)
    await db.commit()

    access_token = create_access_token(data={"sub": user.username, "id": user.id, "email": user.email})
    refresh_token = create_refresh_token(data={"sub": user.username, "id": user.id, "email": user.email})
    return {"access_token": access_token, "refresh_token": refresh_token, "access_type": "bearer"}


@router_v1.post("/refresh-token")
async def refresh_token(refresh_token: str, db: AsyncSession = Depends(get_async_postgres_db)) -> dict:
    """
    Обновляет access_token с помощью refresh_token.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception from None

    result = await db.scalars(select(UserModel).where(UserModel.username == username, UserModel.is_active.is_(True)))
    user = result.first()
    if user is None:
        raise credentials_exception
    access_token = create_access_token(data={"sub": user.username, "id": user.id, "email": user.email})
    return {"access_token": access_token, "token_type": "bearer"}


@router_v1.patch("/update", response_model=UserFullSchema, status_code=status.HTTP_200_OK)
async def update_user_profile(
    user_info: UserUpdateProfile,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> UserModel:
    """Обновляет профиль пользователя"""

    result = await db.execute(
        update(UserModel)
        .where(UserModel.id == current_user.id)
        .values(**user_info.model_dump(exclude_unset=True, by_alias=False))
        .returning(UserModel)
    )

    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    await db.commit()

    return cast(UserModel, user)
