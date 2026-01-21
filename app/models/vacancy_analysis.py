import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, types
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import Base


if TYPE_CHECKING:
    from app.models.users import User
    from app.models.vacancies import Vacancy


class VacancyAnalysis(Base):
    """
    Анализ вакансии от LLM.

    Хранит результаты различных типов анализа:
    - matching: соответствие кандидата вакансии
    - prioritization: оценка привлекательности
    - preparation: подготовка к интервью
    - skill_gap: анализ пробелов в навыках
    - custom: пользовательский промпт
    """

    __tablename__ = "vacancy_analyses"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(types.Uuid, primary_key=True, default=uuid.uuid4)
    # Связь с вакансией
    vacancy_id: Mapped[uuid.UUID] = mapped_column(
        types.Uuid, ForeignKey("vacancies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Связь с пользователем
    user_id: Mapped[uuid.UUID] = mapped_column(types.Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Название анализа -
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # Тип анализа
    analysis_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Шаблон Промпта
    prompt_template: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Кастомный промпт от пользователя
    custom_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Результат анализа в формате JSON
    result_data: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), default=None, nullable=True
    )
    # Текстовый результат анализа
    result_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Какая модель LLM использовалась для анализа
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    # Количество использованных токенов
    tokens_used: Mapped[int | None] = mapped_column(types.Integer, nullable=True)
    # Дата создания записи в БД
    created_at: Mapped[datetime] = mapped_column(
        DateTime().with_variant(TIMESTAMP(timezone=True), "postgresql"), default=lambda: datetime.now(UTC), index=True
    )
    # Дата последнего обновления записи в БД
    updated_at: Mapped[datetime] = mapped_column(
        DateTime().with_variant(TIMESTAMP(timezone=True), "postgresql"),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    vacancy: Mapped["Vacancy"] = relationship("Vacancy", back_populates="analyses")
    user: Mapped["User"] = relationship("User", back_populates="analyses")

    #
    __table_args__ = (
        # Композитный индекс для быстрого поиска анализов вакансии
        Index("ix_vacancy_analyses_vacancy_type_created", "vacancy_id", "analysis_type", "created_at"),
        Index("ix_vacancy_analyses_user_created", "user_id", "created_at"),
        Index("ix_vacancy_analyses_pagination_created", "user_id", "created_at", "id"),
    )

    def __repr__(self) -> str:
        return (
            f"<VacancyAnalysis("
            f"id={self.id}, "
            f"vacancy_id={self.vacancy_id}, "
            f"type={self.analysis_type}, "
            f"created={self.created_at.strftime('%Y-%m-%d %H:%M')}"
            f")>"
        )
