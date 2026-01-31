import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, UniqueConstraint, types
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship


if TYPE_CHECKING:
    from app.models.users import User
    from app.models.vacancies import Vacancy

from app.models.base_model import Base


class UserVacancies(Base):
    """
    Промежуточная таблица для Many-to-Many связи между User и Vacancy.
    """

    __tablename__ = "user_vacancies"

    id: Mapped[uuid.UUID] = mapped_column(types.Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    vacancy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vacancies.id", ondelete="CASCADE"), nullable=False)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime().with_variant(TIMESTAMP(timezone=True), "postgresql"), default=lambda: datetime.now(UTC)
    )

    user: Mapped["User"] = relationship("User", back_populates="user_vacancies")
    vacancy: Mapped["Vacancy"] = relationship("Vacancy", back_populates="user_vacancies")

    __table_args__ = (
        UniqueConstraint("user_id", "vacancy_id", name="uq_user_vacancy"),
        Index("ix_user_vacancies_user_id", "user_id"),
        Index("ix_user_vacancies_vacancy_id", "vacancy_id"),
        Index("ix_user_vacancies_favorite", "user_id", "is_favorite"),
    )
