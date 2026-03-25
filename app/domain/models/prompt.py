"""
Пользовательские промпты.

Domain entity представляющая кастомные промпты пользователя
для переиспользования в диалогах.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, func, types
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.models.base_model import Base


if TYPE_CHECKING:
    from app.domain.models.user import User


class Prompts(Base):
    """
    Пользовательский промпт.

    Domain entity представляющая кастомный промпт пользователя
    для переиспользования в диалогах.

    Attributes:
        id: Уникальный идентификатор (UUID)
        user_id: ID пользователя
        title: Название промпта
        content: Текст промпта
        is_active: Флаг активности (мягкое удаление)
        metadata_: Дополнительные метаданные (JSON)
        created_at: Время создания
        updated_at: Время последнего обновления

    Relationships:
        user: Владелец промпта
    """

    __tablename__ = "prompts"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(types.Uuid, primary_key=True, default=uuid.uuid4)

    # Связь с пользователем
    user_id: Mapped[uuid.UUID] = mapped_column(types.Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Основные поля
    title: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)

    # Метаданные
    metadata_: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), name="metadata")

    # Временные метки
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="prompts")

    # Индексы
    __table_args__ = (
        Index("ix_prompts_user_id_is_active", user_id, is_active),
        Index("ix_prompts_created_at", created_at),
        Index("ix_prompts_pagination", "user_id", "created_at", "id"),
    )
