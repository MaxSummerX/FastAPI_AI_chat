import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, types
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import Base


if TYPE_CHECKING:
    from app.models.messages import Message
    from app.models.users import User


class Conversation(Base):
    """Отдельная беседа/сессия чата"""

    __tablename__ = "conversations"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(types.Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(types.Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    is_archived: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    # import
    source: Mapped[str | None] = mapped_column(String(20), default=None)
    source_id: Mapped[uuid.UUID | None] = mapped_column(types.Uuid, default=None)
    is_imported: Mapped[bool] = mapped_column(default=False, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="conversations")

    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.timestamp"
    )

    # Индексы
    __table_args__ = (
        Index("ix_conversations_user_id", "user_id"),
        Index("ix_conversations_user_updated", "user_id", "updated_at"),
        Index("ix_conversations_pagination", "user_id", "created_at", "id"),
    )
