from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, types
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import Base


class Invite(Base):
    """Простая модель одноразовых приглашений"""

    __tablename__ = "invites"

    id: Mapped[UUID] = mapped_column(types.Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)

    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Просто ID пользователя, кто использовал
    used_by_user_id: Mapped[UUID] = mapped_column(types.Uuid, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now(UTC))
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    @staticmethod
    def generate_code() -> str:
        """Генерирует случайный код приглашения"""
        import secrets

        return secrets.token_urlsafe(16)  # ~22 символа

    def __repr__(self) -> str:
        return f"<Invite(code={self.code[:8]}..., used={self.is_used})>"
