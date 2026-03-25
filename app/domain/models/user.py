"""
Пользователь системы.

Domain entity представляющая пользователя приложения.
Содержит учетные данные, профиль, настройки и связи с другими сущностями.
"""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Index, String, Text, types
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums.role import UserRole
from app.domain.models.base_model import Base


if TYPE_CHECKING:
    from app.domain.models.conversation import Conversation
    from app.domain.models.document import Document
    from app.domain.models.fact import Fact
    from app.domain.models.prompt import Prompts
    from app.domain.models.user_vacancies import UserVacancies
    from app.domain.models.vacancy import VacancyAnalysis


class User(Base):
    """
    Пользователь системы.

    Domain entity представляющая пользователя приложения.
    Содержит учетные данные, профиль, настройки и связи с другими сущностями.

    Attributes:
        id: Уникальный идентификатор (UUID)
        username: Уникальное имя пользователя (макс. 50 символов)
        email: Уникальный email адрес
        password_hash: Хеш пароля (bcrypt)
        first_name: Имя пользователя
        last_name: Фамилия пользователя
        avatar_url: Ссылка на аватар
        bio: Биография/описание
        resume: Резюме в текстовом формате
        phone_number: Номер телефона
        preferred_language: Предпочитаемый язык (default="en")
        timezone: Часовой пояс (default="UTC")
        role: Роль пользователя (USER/ADMIN)
        is_active: Флаг активности (для soft delete)
        is_verified: Флаг верификации email
        settings: JSON настройки пользователя (тема, AI модель и т.д.)
        last_login: Время последнего входа
        created_at: Время создания записи
        updated_at: Время последнего обновления

    Relationships:
        conversations: Список диалогов пользователя
        facts: Факты о пользователе (для AI контекста)
        prompts: Кастомные промпты
        documents: Документы пользователя
        user_vacancies: Связь с сохранёнными вакансиями
        analyses: Анализы вакансий

    Business rules:
        - username и email должны быть уникальны
        - password_hash хранится в виде bcrypt хеша
        - при is_active=False пользователь не может авторизоваться
    """

    __tablename__ = "users"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(types.Uuid, primary_key=True, default=uuid.uuid4)

    # Auth данные
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Базовая информация
    first_name: Mapped[str | None] = mapped_column(String(50))
    last_name: Mapped[str | None] = mapped_column(String(50))
    avatar_url: Mapped[str | None] = mapped_column(String(200))
    bio: Mapped[str | None] = mapped_column(Text)
    resume: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Контактные данные
    phone_number: Mapped[str | None] = mapped_column(String(20))

    # Локализация
    preferred_language: Mapped[str] = mapped_column(String(10), default="en")
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")

    # Статусы
    is_active: Mapped[bool] = mapped_column(default=True)
    is_verified: Mapped[bool] = mapped_column(default=False)

    # Роль пользователя
    role: Mapped[UserRole] = mapped_column(
        types.Enum(UserRole, native_enum=False, length=20),
        default=UserRole.USER,
        nullable=False,
    )

    # Настройки через with_variant - задаём специфичные настройки типа данных для postgresql
    settings: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))

    # Временные метки
    created_at: Mapped[datetime] = mapped_column(
        DateTime().with_variant(TIMESTAMP(timezone=True), "postgresql"), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime().with_variant(TIMESTAMP(timezone=True), "postgresql"),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="user", cascade="all, delete-orphan"
    )

    facts: Mapped[list["Fact"]] = relationship("Fact", back_populates="user", cascade="all, delete-orphan")

    prompts: Mapped[list["Prompts"]] = relationship("Prompts", back_populates="user", cascade="all, delete-orphan")

    user_vacancies: Mapped[list["UserVacancies"]] = relationship(
        "UserVacancies", back_populates="user", cascade="all, delete-orphan"
    )

    analyses: Mapped[list["VacancyAnalysis"]] = relationship(
        "VacancyAnalysis", back_populates="user", cascade="all, delete-orphan"
    )

    documents: Mapped[list["Document"]] = relationship("Document", back_populates="user", cascade="all, delete-orphan")

    # Индексы
    __table_args__ = (
        Index("ix_users_email", "email"),
        Index("ix_users_username", "username"),
    )
