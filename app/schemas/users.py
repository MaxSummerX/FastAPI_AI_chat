import re
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class UserRegister(BaseModel):
    """
    Модель для регистрации пользователя.
    Используется в POST-запросах.
    """

    username: str = Field(..., min_length=3, max_length=50, description="Имя пользователя")
    email: EmailStr = Field(..., max_length=255, description="Email пользователя")
    password: str = Field(..., min_length=8, max_length=255, description="Пароль (минимум 8 символов)")

    @field_validator("password")
    @classmethod
    def password_complexity(cls, value: str) -> str:
        if not re.search(r"[A-Z]", value):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Пароль должен содержать хотя бы одну заглавную букву",
            )
        if not re.search(r"[a-z]", value):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Пароль должен содержать хотя бы одну строчную букву",
            )
        if not re.search(r"\d", value):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Пароль должен содержать хотя бы одну цифру"
            )
        if not re.search(r"[!@#$%^&*()_}:.<>?]", value):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Пароль должен содержать хотя бы один специальный символ !@#$%^&*()_}:.<>?",
            )

        return value


class UserUpdateAuth(BaseModel):
    # TODO: Переработать класс для обновления данных авторизации, нужно атомизировать на отдельные параметры и сделать отдельные endpoints для каждого параметра
    """
    Модель для обновления основных данных пользователя.
    Используется в PUT-запросах.
    """

    username: str | None = Field(None, min_length=3, max_length=50, description="Имя пользователя")
    email: EmailStr | None = Field(None, max_length=255, description="Email пользователя")
    password: str | None = Field(None, min_length=8, max_length=255, description="Пароль (минимум 8 символов)")


class UserUpdateProfile(BaseModel):
    """
    Модель для обновления дополнительных данных пользователя.
    Используется в PUT-запросах.
    """

    first_name: str | None = Field(None, max_length=50, description="Имя")
    last_name: str | None = Field(None, max_length=50, description="Фамилия")
    avatar_url: str | None = Field(None, max_length=200, description="URL аватара")
    bio: str | None = Field(None, description="Биография")
    phone_number: str | None = Field(None, max_length=20, description="Номер телефона")
    preferred_language: str | None = Field(None, max_length=10, description="Предпочитаемый язык")
    timezone: str | None = Field(None, max_length=50, description="Часовой пояс")
    settings: dict | None = Field(None, description="Настройки")


class UserResponseBase(BaseModel):
    """
    Модель для ответа с основными данными пользователя.
    Используется в POST, PUT и GET запросах.
    """

    id: UUID = Field(description="UUID пользователя")
    username: str = Field(description="Имя пользователя")
    email: EmailStr = Field(description="Email пользователя")
    is_active: bool = Field(description="Активность пользователя")
    is_verified: bool = Field(description="Проверен ли пользователь")

    model_config = ConfigDict(from_attributes=True)


class UserResponseFull(UserResponseBase):
    """
    Модель для ответа с дополнительными данными пользователя.
    Используется в PUT и GET-запросах.
    """

    first_name: str | None = Field(None, description="Имя")
    last_name: str | None = Field(None, description="Фамилия")
    avatar_url: str | None = Field(None, description="URL аватара")
    bio: str | None = Field(None, description="Биография")
    phone_number: str | None = Field(None, description="Номер телефона")
    preferred_language: str = Field(description="Предпочитаемый язык")
    timezone: str = Field(description="Часовой пояс")
    settings: dict | None = Field(None, description="Настройки")
    created_at: datetime = Field(description="Дата создания")
    updated_at: datetime = Field(description="Дата обновления")
    last_login: datetime | None = Field(None, description="Последний вход")

    model_config = ConfigDict(from_attributes=True)
