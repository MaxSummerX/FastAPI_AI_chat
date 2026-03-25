"""
Анализ вакансии от LLM.

Domain entity представляющая результаты анализа вакансии
с помощью больших языковых моделей.
"""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, types
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.models.base_model import Base


if TYPE_CHECKING:
    from app.domain.models.user import User
    from app.domain.models.vacancy import Vacancy


class VacancyAnalysis(Base):
    """
    Анализ вакансии от LLM.

    Domain entity представляющая результаты анализа вакансии
    с помощью больших языковых моделей.

    Attributes:
        id: Уникальный идентификатор (UUID)
        vacancy_id: ID вакансии
        user_id: ID пользователя
        title: Название анализа
        analysis_type: Тип анализа (matching/prioritization/preparation/skill_gap/custom)
        prompt_template: Шаблон промпта
        custom_prompt: Кастомный промпт
        result_data: Результат анализа (JSON)
        result_text: Текстовый результат
        model_used: Использованная модель LLM
        tokens_used: Количество токенов
        created_at: Время создания
        updated_at: Время последнего обновления

    Relationships:
        vacancy: Анализируемая вакансия
        user: Пользователь, создавший анализ
    """

    __tablename__ = "vacancy_analyses"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(types.Uuid, primary_key=True, default=uuid.uuid4)

    # Связи
    vacancy_id: Mapped[uuid.UUID] = mapped_column(
        types.Uuid, ForeignKey("vacancies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(types.Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Основные поля
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    analysis_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    prompt_template: Mapped[str | None] = mapped_column(String(100), nullable=True)
    custom_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Результаты анализа
    result_data: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), default=None, nullable=True
    )
    result_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # AI метаданные
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(types.Integer, nullable=True)

    # Временные метки
    created_at: Mapped[datetime] = mapped_column(
        DateTime().with_variant(TIMESTAMP(timezone=True), "postgresql"), default=lambda: datetime.now(UTC), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime().with_variant(TIMESTAMP(timezone=True), "postgresql"),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    vacancy: Mapped["Vacancy"] = relationship("Vacancy", back_populates="analyses")
    user: Mapped["User"] = relationship("User", back_populates="analyses")

    # Индексы
    __table_args__ = (
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
