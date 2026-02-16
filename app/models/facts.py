import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Text, types
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enum.facts import FactCategory, FactSource
from app.models.base_model import Base


if TYPE_CHECKING:
    from app.models.conversations import Conversation
    from app.models.messages import Message
    from app.models.users import User


class Fact(Base):
    """Извлечённый факт о пользователе"""

    __tablename__ = "facts"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(types.Uuid, primary_key=True, default=uuid.uuid4)
    # Связь с пользователем
    user_id: Mapped[uuid.UUID] = mapped_column(types.Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Факт о пользователе
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Категория факта
    category: Mapped[FactCategory] = mapped_column(SQLEnum(FactCategory))

    # Источник факта
    source_type: Mapped[FactSource] = mapped_column(SQLEnum(FactSource), default=FactSource.EXTRACTED)

    # Откуда извлечён факт (опционально, для EXTRACTED)
    source_conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        types.Uuid, ForeignKey("conversations.id", ondelete="SET NULL")
    )
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        types.Uuid, ForeignKey("messages.id", ondelete="SET NULL")
    )

    # Confidence score от LLM
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    # 0.0 - 1.0, насколько уверены в факте

    # Для обновления устаревших фактов
    is_active: Mapped[bool] = mapped_column(default=True)

    # Если факт устарел и заменён новым
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(types.Uuid, ForeignKey("facts.id", ondelete="SET NULL"))

    # Временные метки
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Когда последний раз подтверждался в диалогах
    last_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Метаданные
    metadata_: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), name="metadata")

    # ID в mem0ai
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
