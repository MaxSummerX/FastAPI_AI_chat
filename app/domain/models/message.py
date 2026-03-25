"""
Сообщения в чате.

Domain entity представляющая отдельное сообщение в беседе.
Содержит роль, контент, метаданные и связь с диалогом.
"""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, types
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums.message import MessageRole
from app.domain.models.base_model import Base


if TYPE_CHECKING:
    from app.domain.models.conversation import Conversation


class Message(Base):
    """
    Отдельное сообщение в чате.

    Attributes:
        id: Уникальный идентификатор (UUID)
        conversation_id: ID беседы
        role: Роль отправителя (user/assistant/system)
        content: Текст сообщения
        timestamp: Время создания сообщения
        source: Источник импорта
        source_id: ID в источнике импорта
        is_imported: Флаг импортированного сообщения
        tokens_used: Количество использованных токенов
        model: Название модели AI
        metadata_: Дополнительные метаданные (JSON)
        edited_at: Время последнего редактирования
        is_deleted: Флаг удаления (мягкое)

    Relationships:
        conversation: Беседа, содержащая сообщение
    """

    __tablename__ = "messages"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(types.Uuid, primary_key=True, default=uuid.uuid4)

    # Связь с беседой
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        types.Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )

    # Содержимое сообщения
    role: Mapped[str] = mapped_column(SQLEnum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Import метаинформация
    source: Mapped[str | None] = mapped_column(String(20), default=None)
    source_id: Mapped[uuid.UUID | None] = mapped_column(types.Uuid, default=None)
    is_imported: Mapped[bool] = mapped_column(default=False, nullable=True)

    # AI метаданные
    tokens_used: Mapped[int | None] = mapped_column()
    model: Mapped[str] = mapped_column(String(50))

    # Дополнительные данные - name="metadata" чтобы не конфликтовать с SQLAlchemy
    metadata_: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), name="metadata")

    # Редактирование и удаление
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_deleted: Mapped[bool] = mapped_column(default=False)

    # Relationships
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")

    # Индексы
    __table_args__ = (
        Index("ix_messages_conversation_id", "conversation_id"),
        Index("ix_messages_conversation_timestamp", "conversation_id", "timestamp"),
        Index("ix_messages_pagination", "conversation_id", "timestamp", "id"),
    )
