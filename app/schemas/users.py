import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class BaseUser(BaseModel):
    """
    Базовая схема пользователя для работы паролями
    """

    password: str = Field(..., min_length=8, max_length=255, description="Пароль (минимум 8 символов)")

    @field_validator("password")
    @classmethod
    def password_complexity(cls, value: str) -> str:
        """
        Валидация сложности пароля.

        Требования:
        - Минимум 1 заглавная буква
        - Минимум 1 строчная буква
        - Минимум 1 цифра
        - Минимум 1 спецсимвол
        """
        requirements = []

        if not re.search(r"[A-Z]", value):
            requirements.append("one uppercase letter")

        if not re.search(r"[a-z]", value):
            requirements.append("one lowercase letter")

        if not re.search(r"\d", value):
            requirements.append("one digit")

        if not re.search(r"[!@#$%^&*()_{}:.<>?]", value):
            requirements.append("one special character (!@#$%^&*()_{}:.<>?)")

        if requirements:
            missing = ", ".join(requirements)
            raise ValueError(f"Password must contain at least: {missing}")

        return value


class UserRegister(BaseUser):
    """
    Схема для регистрации пользователя.
    Используется в POST-запросах.
    """

    username: str = Field(..., min_length=3, max_length=50, description="Имя пользователя")
    email: EmailStr = Field(..., max_length=255, description="Email пользователя")


class UserUpdatePassword(BaseUser):
    """Схема для обновления пароля"""

    current_password: str = Field(..., description="Текущий пароль")


class UserUpdateEmail(BaseModel):
    """Схема для обновления email с подтверждением"""

    current_password: str = Field(..., description="Текущий пароль")
    new_email: EmailStr = Field(..., max_length=255, description="Email пользователя")


class UserUpdateUsername(BaseModel):
    """Схема для обновления username"""

    current_password: str = Field(..., description="Текущий пароль")
    username: str = Field(..., min_length=3, max_length=50, description="Имя пользователя")


class UserUpdateProfile(BaseModel):
    """
    Схема для обновления дополнительных данных пользователя.
    Используется в PATCH-запросах.
    """

    first_name: str | None = Field(None, max_length=50, description="Имя")
    last_name: str | None = Field(None, max_length=50, description="Фамилия")
    avatar_url: str | None = Field(None, max_length=200, description="URL аватара")
    bio: str | None = Field(None, max_length=1000, description="Биография")
    phone_number: str | None = Field(None, max_length=20, pattern="^[+0-9]+$", description="Номер телефона")
    preferred_language: str | None = Field(None, max_length=10, description="Предпочитаемый язык")
    timezone: str | None = Field(None, max_length=50, description="Часовой пояс")
    settings: dict | None = Field(None, description="Настройки")
    resume: str | None = Field(None, min_length=10, max_length=50000, description="Резюме пользователя (текст)")

    @field_validator("resume")
    @classmethod
    def validate_resume_not_empty(cls, v: str | None) -> str | None:
        """Проверка, что резюме не состоит только из пробелов"""
        if v is not None and not v.strip():
            raise ValueError("Резюме не может быть пустым или только из пробелов")
        return v


class UserResponseBase(BaseModel):
    """
    Схема для ответа с основными данными пользователя.
    Используется в POST, PATCH и GET запросах.
    """

    id: UUID = Field(description="UUID пользователя")
    username: str = Field(description="Имя пользователя")
    email: EmailStr = Field(description="Email пользователя")
    is_active: bool = Field(description="Активность пользователя")
    is_verified: bool = Field(description="Проверен ли пользователь")

    model_config = ConfigDict(from_attributes=True)


class UserResponseFull(UserResponseBase):
    """
    Схема для ответа с дополнительными данными пользователя.
    Используется в PATCH и GET-запросах.
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
    resume: str | None = Field(None, description="Резюме пользователя")

    model_config = ConfigDict(from_attributes=True)
