from typing import cast

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_config import ALGORITHM, SECRET_KEY
from app.depends.db_depends import get_async_postgres_db
from app.enum.roles import UserRole
from app.models.users import User as UserModel


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v2/user/token")


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_async_postgres_db)
) -> UserModel:
    """
    Проверяет JWT и возвращает пользователя из базы.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired", headers={"WWW-Authenticate": "Bearer"}
        ) from None

    except jwt.PyJWTError as exc:
        raise credentials_exception from exc

    result = await db.scalars(select(UserModel).where(UserModel.username == username, UserModel.is_active))
    user = cast(UserModel | None, result.first())

    if user is None:
        raise credentials_exception

    return user


async def get_current_admin_user(current_user: UserModel = Depends(get_current_user)) -> UserModel:
    """
    Проверяет что текущий пользователь имеет роль администратора.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user
