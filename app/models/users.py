import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Index, String, Text, types
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import Base


if TYPE_CHECKING:
    from app.models.conversations import Conversation
    from app.models.facts import Fact


class User(Base):
    """Данные пользователя"""

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

    # Контактные данные (опционально)
    phone_number: Mapped[str | None] = mapped_column(String(20))

    # Локализация
    preferred_language: Mapped[str] = mapped_column(String(10), default="en")
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")

    # Статусы
    is_active: Mapped[bool] = mapped_column(default=True)
    is_verified: Mapped[bool] = mapped_column(default=False)

    # Настройки (через with_variant - задаём специфичные настройки типа данных для postgresql)
    settings: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    # Пример: {"theme": "dark", "ai_model": "llama3", "notifications": true}

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

    # Relationship
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="user", cascade="all, delete-orphan"
    )

    facts: Mapped[list["Fact"]] = relationship("Fact", back_populates="user", cascade="all, delete-orphan")

    # Индексы
    __table_args__ = (
        Index("ix_users_email", "email"),
        Index("ix_users_username", "username"),
    )
