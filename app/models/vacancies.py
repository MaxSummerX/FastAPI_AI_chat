import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Index, Numeric, String, Text, types
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import Base


if TYPE_CHECKING:
    from app.models.user_vacancies import UserVacancies
    from app.models.vacancy_analysis import VacancyAnalysis


class Vacancy(Base):
    """
    Данные вакансии от HeadHunter.

    Одна вакансия может иметь множество анализов от LLM
    (соответствие, привлекательность, подготовка и т.д.).
    """

    __tablename__ = "vacancies"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(types.Uuid, primary_key=True, default=uuid.uuid4)
    # id headhunter
    hh_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    # По какому запросу была найдена впервые вакансия
    query_request: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    # Название вакансии
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    # Описание вакансии
    description: Mapped[str | None] = mapped_column(Text, default=None)
    # Зарплата от (вынесено для фильтрации)
    salary_from: Mapped[int | None] = mapped_column(Numeric(10, 2), nullable=True, index=True)
    # Зарплата до
    salary_to: Mapped[int | None] = mapped_column(Numeric(10, 2), nullable=True, index=True)
    # Валюта зарплаты
    salary_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    # Gross или Net (до вычета налогов или после)
    salary_gross: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # ID опыта (noExperience, between1And3, between3And6, moreThan6)
    experience_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    # ID города
    area_id: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    # Название города
    area_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # ID графика (remote, fullDay, flex, shift, etc.)
    schedule_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    # ID типа занятости (full, part, project, etc.)
    employment_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    # ID работодателя из HeadHunter
    employer_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    # Название компании-работодателя
    employer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Ссылка на вакансию на hh.ru
    hh_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Ссылка для отклика на вакансию
    apply_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Активна ли вакансия (для внутренней логики)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # Архивная ли вакансия (на hh.ru)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # Json данные
    raw_data: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), default=None)

    # Дата публикации на hh.ru
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime().with_variant(TIMESTAMP(timezone=True), "postgresql"), nullable=True, index=True
    )
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
    user_vacancies: Mapped[list["UserVacancies"]] = relationship(
        "UserVacancies", back_populates="vacancy", cascade="all, delete-orphan"
    )
    analyses: Mapped[list["VacancyAnalysis"]] = relationship(
        "VacancyAnalysis", back_populates="vacancy", cascade="all, delete-orphan"
    )

    # Индексы
    __table_args__ = (
        # GIN индекс для полнотекстового поиска по JSON
        Index("ix_vacancies_new_raw_data_gin", "raw_data", postgresql_using="gin"),
        # Композитные индексы для частых запросов
        Index("ix_vacancies_new_salary_area", "salary_from", "area_id"),
        Index("ix_vacancies_new_experience_schedule", "experience_id", "schedule_id"),
        Index("ix_vacancies_new_published", "published_at", "is_active"),
        Index("ix_vacancies_pagination_created", "created_at", "id"),
        Index("ix_vacancies_pagination_published", "published_at", "id"),
    )

    def is_stale(self, days: int = 30) -> bool:
        """
        Проверяет, устарела ли вакансия (не обновлялась N дней).
        """
        days_since_update: timedelta = datetime.now(UTC) - self.updated_at
        return days_since_update > timedelta(days=days)

    @property
    def salary_display(self) -> str | None:
        """
        Форматирует зарплату для отображения.
        """
        if not self.salary_from and not self.salary_to:
            return None

        currency = self.salary_currency or "RUR"
        gross_suffix = "до вычета" if self.salary_gross else "на руки"

        if self.salary_from and self.salary_to:
            return f"{int(self.salary_from)} - {int(self.salary_to)} {currency} ({gross_suffix})"
        elif self.salary_from:
            return f"от {int(self.salary_from)} {currency} ({gross_suffix})"
        elif self.salary_to:
            return f"до {int(self.salary_to)} {currency} ({gross_suffix})"
        else:
            return "Зарплата не указана"
