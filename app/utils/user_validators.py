from uuid import UUID

from fastapi import HTTPException, status
from loguru import logger
from pydantic import EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.users import User as UserModel


ERROR_USERNAME_EXISTS = "Username already registered"
ERROR_EMAIL_EXISTS = "Email already registered"


async def validate_user_unique(
    db: AsyncSession,
    username: str,
    email: str | EmailStr,
    exclude_user_id: UUID | None = None,
) -> None:
    """
    Проверяет уникальность username и email.

    Args:
        db: Асинхронная сессия БД
        username: Имя пользователя для проверки
        email: Email для проверки
        exclude_user_id: ID пользователя для исключения из проверки
                        (используется при обновлении профиля)
    """
    try:
        # Проверка уникальности username
        username_query = select(UserModel).where(UserModel.username == username)

        # Исключаем текущего пользователя при обновлении
        if exclude_user_id:
            username_query = username_query.where(UserModel.id != exclude_user_id)

        username_result = await db.scalars(username_query)

        if username_result.first():
            logger.warning(f"Попытка регистрации с существующим username: {username}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ERROR_USERNAME_EXISTS,
            )

        # Проверка уникальности email
        email_query = select(UserModel).where(UserModel.email == email)

        # Исключаем текущего пользователя при обновлении
        if exclude_user_id:
            email_query = email_query.where(UserModel.id != exclude_user_id)

        email_result = await db.scalars(email_query)

        if email_result.first():
            logger.warning(f"Попытка регистрации с существующим email: {email}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=ERROR_EMAIL_EXISTS,
            )

    except HTTPException:
        # Пробрасываем HTTPException дальше
        raise
    except Exception as e:
        # Логируем неожиданные ошибки
        logger.error(f"Ошибка при валидации пользователя: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error validating user data",
        ) from e
