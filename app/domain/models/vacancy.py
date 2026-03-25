"""
Вакансии с HeadHunter.

Domain entity представляющая вакансии, импортированные с hh.ru.
Содержит данные о вакансии и связи с анализами.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Index, Numeric, String, Text, types
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.models.base_model import Base


if TYPE_CHECKING:
    from app.domain.models.user_vacancies import UserVacancies
    from app.domain.models.vacancy_analysis import VacancyAnalysis


class Vacancy(Base):
    """
    Вакансия с HeadHunter.

    Domain entity представляющая вакансию, импортированную с hh.ru.
    Одна вакансия может иметь множество анализов от LLM.

    Attributes:
        id: Уникальный идентификатор (UUID)
        hh_id: ID вакансии на hh.ru
        query_request: Поисковый запрос для поиска вакансии
        title: Название вакансии
        description: Описание вакансии
        salary_from: Зарплата от
        salary_to: Зарплата до
        salary_currency: Валюта зарплаты
        salary_gross: Gross или Net
        experience_id: ID уровня опыта
        area_id: ID города
        area_name: Название города
        schedule_id: ID графика работы
        employment_id: ID типа занятости
        employer_id: ID работодателя
        employer_name: Название компании
        hh_url: Ссылка на вакансию на hh.ru
        apply_url: Ссылка для отклика
        is_archived: Флаг архивации
        raw_data: Сырые данные JSON с hh.ru
        published_at: Дата публикации на hh.ru
        created_at: Время создания записи
        updated_at: Время последнего обновления

    Relationships:
        user_vacancies: Связи с пользователями
        analyses: Анализы вакансии
    """

    __tablename__ = "vacancies"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(types.Uuid, primary_key=True, default=uuid.uuid4)

    # Идентификаторы hh.ru
    hh_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    query_request: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # Основная информация
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    employer_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    employer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Зарплата
    salary_from: Mapped[int | None] = mapped_column(Numeric(10, 2), nullable=True, index=True)
    salary_to: Mapped[int | None] = mapped_column(Numeric(10, 2), nullable=True, index=True)
    salary_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    salary_gross: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Локация и график
    area_id: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    area_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    schedule_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    employment_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    # ID опыта (noExperience, between1And3, between3And6, moreThan6)
    experience_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)

    # Ссылки
    hh_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    apply_url: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Статус и сырые данные
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    raw_data: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), default=None)

    # Временные метки
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime().with_variant(TIMESTAMP(timezone=True), "postgresql"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime().with_variant(TIMESTAMP(timezone=True), "postgresql"), default=lambda: datetime.now(UTC), index=True
    )
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
        Index("ix_vacancies_new_raw_data_gin", "raw_data", postgresql_using="gin"),
        Index("ix_vacancies_new_salary_area", "salary_from", "area_id"),
        Index("ix_vacancies_new_experience_schedule", "experience_id", "schedule_id"),
        Index("ix_vacancies_new_published", "published_at"),
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
