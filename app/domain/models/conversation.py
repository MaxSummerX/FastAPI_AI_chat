"""
Диалоги/сессии чата.

Domain entity представляющая отдельную беседу пользователя с AI.
Содержит сообщения, документы и связь с пользователем.
"""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, types
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.models.base_model import Base


if TYPE_CHECKING:
    from app.domain.models.document import Document
    from app.domain.models.message import Message
    from app.domain.models.user import User


class Conversation(Base):
    """
    Отдельная беседа/сессия чата.

    Attributes:
        id: Уникальный идентификатор (UUID)
        user_id: ID пользователя
        title: Название беседы
        is_archived: Флаг архивации (мягкое удаление)
        source: Источник импорта (если импортирован)
        source_id: ID в источнике импорта
        is_imported: Флаг импортированной беседы
        created_at: Время создания
        updated_at: Время последнего обновления

    Relationships:
        user: Владелец беседы
        messages: Сообщения в беседе
        documents: Документы, созданные из беседы
    """

    __tablename__ = "conversations"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(types.Uuid, primary_key=True, default=uuid.uuid4)

    # Связь с пользователем
    user_id: Mapped[uuid.UUID] = mapped_column(types.Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Основные поля
    title: Mapped[str | None] = mapped_column(String(255))
    is_archived: Mapped[bool] = mapped_column(default=False)

    # Временные метки
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Import метаинформация
    source: Mapped[str | None] = mapped_column(String(20), default=None)
    source_id: Mapped[uuid.UUID | None] = mapped_column(types.Uuid, default=None)
    is_imported: Mapped[bool] = mapped_column(default=False, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="conversations")

    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.timestamp"
    )

    documents: Mapped[list["Document"]] = relationship(
        "Document", back_populates="conversation", order_by="Document.created_at"
    )

    # Индексы
    __table_args__ = (
        Index("ix_conversations_user_id", "user_id"),
        Index("ix_conversations_user_updated", "user_id", "updated_at"),
        Index("ix_conversations_pagination", "user_id", "created_at", "id"),
    )
