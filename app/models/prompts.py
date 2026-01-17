import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, func, types
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import Base


if TYPE_CHECKING:
    from app.models.users import User


class Prompts(Base):
    """Модель пользовательских промптов"""

    __tablename__ = "prompts"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(types.Uuid, primary_key=True, default=uuid.uuid4)

    # Связь с пользователем
    user_id: Mapped[uuid.UUID] = mapped_column(types.Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Название
    title: Mapped[str | None] = mapped_column(String(255))

    # Prompt пользователя
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Для мягкого удаления
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

    __table_args__ = (
        Index("ix_prompts_user_id_is_active", user_id, is_active),
        Index("ix_prompts_created_at", created_at),
        Index("ix_prompts_pagination", "user_id", "created_at", "id"),
    )
