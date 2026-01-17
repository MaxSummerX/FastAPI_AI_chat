import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Text, types
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import Base


if TYPE_CHECKING:
    from app.models.conversations import Conversation
    from app.models.messages import Message
    from app.models.users import User


class FactCategory(str, Enum):
    """Категории фактов"""

    PERSONAL = "personal"  # Личная информация
    PROFESSIONAL = "professional"  # Работа, навыки
    PREFERENCES = "preferences"  # Предпочтения
    LEARNING = "learning"  # Что изучает
    GOALS = "goals"  # Цели
    INTERESTS = "interests"  # Интересы
    TECHNICAL = "technical"  # Технические знания
    BEHAVIORAL = "behavioral"  # Паттерны поведения


class FactSource(str, Enum):
    """Источник факта"""

    EXTRACTED = "extracted"  # Автоматически извлечён из диалога
    USER_PROVIDED = "user_provided"  # Добавлен пользователем вручную
    IMPORTED = "imported"  # Импортирован из внешнего источника
    INFERRED = "inferred"  # Выведен AI на основе нескольких фактов


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

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="facts")

    # Временные метки
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Когда последний раз подтверждался в диалогах
    last_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Метаданные
    metadata_: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), name="metadata")

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
