from typing import cast

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.auth import create_access_token, create_refresh_token, hash_password, verify_password
from app.config import ALGORITHM, SECRET_KEY
from app.depends.db_depends import get_async_postgres_db
from app.models.users import User as UserModel
from app.schemas.users import UserRegister
from app.schemas.users import UserResponseBase as UserSchema


router_v1 = APIRouter(prefix="/users", tags=["users"])


@router_v1.post("/register", response_model=UserSchema, status_code=status.HTTP_201_CREATED)
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

    # Создание объекта пользователя с хешированием пароля
    db_user = UserModel(username=user.username, email=user.email, password_hash=hash_password(user.password))

    # Добавляем в сессию и сохранение в базе
    db.add(db_user)
    await db.commit()
    return db_user


@router_v1.post("/token")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_async_postgres_db)
) -> dict:
    """
    Аутентифицирует пользователя и возвращает JWT с email, id.
    """
    result = await db.scalars(select(UserModel).where(UserModel.username == form_data.username, UserModel.is_active))
    user = cast(UserModel, result.first())

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
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
