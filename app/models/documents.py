import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, types
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enum.documents import DocumentCategory
from app.models.base_model import Base


if TYPE_CHECKING:
    from app.models.conversations import Conversation
    from app.models.users import User


class Document(Base):
    """Документы пользователя для хранения текстовых данных, заметок и другого контента"""

    __tablename__ = "documents"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(types.Uuid, primary_key=True, default=uuid.uuid4)
    # Связь с пользователем
    user_id: Mapped[uuid.UUID] = mapped_column(types.Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Название документа
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Архивирован ли документ (мягкое удаление)
    is_archived: Mapped[bool] = mapped_column(default=False)
    # Содержимое документа (основной текст)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Категория документа (заметка, письмо, статья и т.д.)
    category: Mapped[DocumentCategory] = mapped_column(SQLEnum(DocumentCategory), default=DocumentCategory.NOTE)
    # Временные метки
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
    # Метаданные документа (произвольные данные в формате JSON)
    metadata_: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), name="metadata", nullable=True
    )
    # Тэги для организации и поиска документов
    tags: Mapped[list[str] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), name="tags", nullable=True
    )
    # ID векторного представления в Qdrant для семантического поиска
    summary_qdrant_id: Mapped[uuid.UUID | None] = mapped_column(types.Uuid, nullable=True)
    # Краткое описание/саммари документа (генерируется AI)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Флаг отвечающий за актуальность саммари
    summary_outdated: Mapped[bool] = mapped_column(default=False, nullable=False)
    # ID диалога-источника (если документ создан из диалога)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        types.Uuid, ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    # ID сообщения-источника (если документ создан из сообщения)
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
    )
