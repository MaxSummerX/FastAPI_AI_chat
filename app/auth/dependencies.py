from typing import cast

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ALGORITHM, SECRET_KEY
from app.depends.db_depends import get_async_postgres_db
from app.models.users import User as UserModel


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="users/token")


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
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired", headers={"WWW-Authenticate": "Bearer"}
        ) from None

    except jwt.PyJWTError as exc:
        raise credentials_exception from exc

    result = await db.scalars(select(UserModel).where(UserModel.email == email, UserModel.is_active))
    user = cast(UserModel | None, result.first())

    if user is None:
        raise credentials_exception

    return user
