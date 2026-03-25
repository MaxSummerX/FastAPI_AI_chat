"""
Факты о пользователях.

Domain entity представляющая извлечённую информацию о пользователе
для персонализации AI-ответов. Используется в системе памяти.
"""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Text, types
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums.fact import FactCategory, FactSource
from app.domain.models.base_model import Base


if TYPE_CHECKING:
    from app.domain.models.conversation import Conversation
    from app.domain.models.message import Message
    from app.domain.models.user import User


class Fact(Base):
    """
    Извлечённый факт о пользователе.

    Domain entity представляющая информацию о пользователе
    для персонализации AI-ответов.

    Attributes:
        id: Уникальный идентификатор (UUID)
        user_id: ID пользователя
        content: Текст факта
        category: Категория факта
        source_type: Источник факта (извлечён/вручную/импортирован/выведен)
        source_conversation_id: ID беседы-источника
        source_message_id: ID сообщения-источника
        confidence: Уверенность в факте (0.0 - 1.0)
        is_active: Флаг актуальности
        superseded_by_id: ID факта, который заменил этот
        created_at: Время создания
        last_confirmed_at: Время последнего подтверждения
        metadata_: Дополнительные метаданные (JSON)
        mem0_id: ID в системе mem0ai

    Relationships:
        user: Владелец факта
        source_conversation: Беседа-источник
        source_message: Сообщение-источник
    """

    __tablename__ = "facts"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(types.Uuid, primary_key=True, default=uuid.uuid4)

    # Связь с пользователем
    user_id: Mapped[uuid.UUID] = mapped_column(types.Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Содержимое
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[FactCategory] = mapped_column(SQLEnum(FactCategory))
    source_type: Mapped[FactSource] = mapped_column(SQLEnum(FactSource), default=FactSource.EXTRACTED)

    # Источники факта (опционально, для EXTRACTED)
    source_conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        types.Uuid, ForeignKey("conversations.id", ondelete="SET NULL")
    )
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        types.Uuid, ForeignKey("messages.id", ondelete="SET NULL")
    )

    # Confidence score от LLM (0.0 - 1.0)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    # Статус актуальности
    is_active: Mapped[bool] = mapped_column(default=True)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(types.Uuid, ForeignKey("facts.id", ondelete="SET NULL"))

    # Временные метки
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    last_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Интеграции
    metadata_: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), name="metadata")
    mem0_id: Mapped[types.Uuid | None] = mapped_column(types.Uuid, default=None)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="facts")

    source_conversation: Mapped["Conversation | None"] = relationship(
        "Conversation", foreign_keys=[source_conversation_id]
    )

    source_message: Mapped["Message | None"] = relationship("Message", foreign_keys=[source_message_id])

    # Индексы
    __table_args__ = (
        Index("ix_user_facts_user_id", "user_id"),
        Index("ix_user_facts_user_category", "user_id", "category"),
        Index("ix_user_facts_user_active", "user_id", "is_active"),
        Index("ix_user_facts_source_type", "source_type"),
        Index("ix_user_facts_user_source", "user_id", "source_type"),
        Index("ix_facts_pagination", "user_id", "created_at", "id"),
    )
