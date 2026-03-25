"""
Документы пользователя.

Domain entity представляющая текстовые документы, заметки и другой контент
пользователя с поддержкой полнотекстового поиска.
"""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Computed, DateTime, ForeignKey, Index, String, Text, types
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.enums.document import DocumentCategory
from app.domain.models.base_model import Base


if TYPE_CHECKING:
    from app.domain.models.conversation import Conversation
    from app.domain.models.user import User


class Document(Base):
    """
    Документ пользователя.

    Domain entity представляющая текстовый документ с поддержкой
    полнотекстового поиска и AI-саммари.

    Attributes:
        id: Уникальный идентификатор (UUID)
        user_id: ID пользователя
        title: Название документа
        is_archived: Флаг архивации (мягкое удаление)
        content: Содержимое документа
        category: Категория документа
        metadata_: Дополнительные метаданные (JSON)
        tags: Теги для организации
        summary_qdrant_id: ID векторного представления в Qdrant
        summary: Краткое описание (генерируется AI)
        summary_outdated: Флаг актуальности саммари
        created_at: Время создания
        updated_at: Время последнего обновления

    Relationships:
        user: Владелец документа
        conversation: Беседа-источник
    """

    __tablename__ = "documents"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(types.Uuid, primary_key=True, default=uuid.uuid4)

    # Связь с пользователем
    user_id: Mapped[uuid.UUID] = mapped_column(types.Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Основные поля
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_archived: Mapped[bool] = mapped_column(default=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[DocumentCategory] = mapped_column(SQLEnum(DocumentCategory), default=DocumentCategory.NOTE)

    # Временные метки
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # Метаданные и теги
    metadata_: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), name="metadata", nullable=True
    )
    tags: Mapped[list[str] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), name="tags", nullable=True
    )

    # AI саммари
    summary_qdrant_id: Mapped[uuid.UUID | None] = mapped_column(types.Uuid, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_outdated: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Полнотекстовый поиск - TSVECTOR для PostgreSQL с весами: A=title, B=summary, C=content
    # persisted=True - хранится на диске, пересчитывается автоматически при изменении
    search_vector = mapped_column(
        TSVECTOR,
        Computed(
            """
            setweight(to_tsvector('russian', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
            setweight(to_tsvector('russian', coalesce(summary, '')), 'B') ||
            setweight(to_tsvector('english', coalesce(summary, '')), 'B') ||
            setweight(to_tsvector('russian', coalesce(content, '')), 'C') ||
            setweight(to_tsvector('english', coalesce(content, '')), 'C')
            """,
            persisted=True,
        ),
        nullable=True,
    )

    # Источники
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        types.Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        types.Uuid, ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="documents")
    conversation: Mapped["Conversation | None"] = relationship("Conversation", back_populates="documents")

    # Индексы
    __table_args__ = (
        Index("ix_user_documents_user_id", "user_id"),
        Index("ix_user_documents_user_category", "user_id", "category"),
        Index("ix_documents_pagination", "user_id", "created_at", "id"),
        Index("ix_documents_conversation", "conversation_id"),
        Index("ix_documents_tags", "tags", postgresql_using="gin"),
        Index("ix_documents_search_vector", "search_vector", postgresql_using="gin"),
    )
