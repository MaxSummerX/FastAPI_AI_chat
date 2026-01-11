from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class VacancyBase(BaseModel):
    """
    Базовая схема для вакансий
    """

    hh_id: str = Field(description="id полученное от HeadHunter", max_length=32)


class VacancyResponse(VacancyBase):
    """
    Схема для ответа с данными о вакансии
    """

    id: UUID = Field(description="UUID вакансии в БД")
    query_request: str = Field(description="Поисковый запрос, по которому была найдена вакансия")
    title: str = Field(description="Название вакансии")
    description: str | None = Field(default=None, description="Описание вакансии")
    salary_from: int | None = Field(default=None, description="Зарплата от")
    salary_to: int | None = Field(default=None, description="Зарплата до")
    salary_currency: str | None = Field(default=None, description="Валюта зарплаты (RUR, USD, EUR)")
    salary_gross: bool | None = Field(default=None, description="True - до вычета налогов, False - на руки")
    experience_id: str | None = Field(default=None, description="ID уровня опыта (noExperience, between1And3, etc.)")
    area_id: str | None = Field(default=None, description="ID города на HeadHunter")
    area_name: str | None = Field(default=None, description="Название города")
    schedule_id: str | None = Field(default=None, description="ID графика работы (fullDay, remote, etc.)")
    employment_id: str | None = Field(default=None, description="ID типа занятости (full, part, etc.)")
    employer_id: str | None = Field(default=None, description="ID работодателя на HeadHunter")
    employer_name: str | None = Field(default=None, description="Название компании-работодателя")
    hh_url: str | None = Field(default=None, description="Ссылка на вакансию на hh.ru")
    apply_url: str | None = Field(default=None, description="Ссылка для отклика на вакансию")
    is_active: bool = Field(description="Активна ли вакансия во внутренней логике")
    is_archived: bool = Field(description="Архивная ли вакансия на hh.ru")
    published_at: datetime | None = Field(default=None, description="Дата публикации на hh.ru")
    created_at: datetime = Field(description="Дата создания записи в БД")
    updated_at: datetime = Field(description="Дата последнего обновления в БД")

    model_config = ConfigDict(from_attributes=True)
