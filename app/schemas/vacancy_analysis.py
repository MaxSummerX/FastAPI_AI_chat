from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.enum.analysis import AnalysisType


class VacancyAnalysisCreate(BaseModel):
    """Базовая схема для анализа вакансии"""

    analysis_type: AnalysisType = Field(description="Тип анализа")
    title: str | None = Field(
        default=None, description="Название (только для CUSTOM типа, для остальных генерируется автоматически)"
    )
    custom_prompt: str | None = Field(default=None, description="Кастомный промпт (обязателен для CUSTOM типа)")


class VacancyBaseResponse(BaseModel):
    """Базовая схема анализа вакансии для ответа"""

    id: UUID = Field(description="ID анализа")
    vacancy_id: UUID = Field(description="ID вакансии")
    title: str = Field(description="Название анализа")
    analysis_type: AnalysisType = Field(description="Тип анализа")
    created_at: datetime = Field(description="Дата создания")

    model_config = ConfigDict(from_attributes=True)


class VacancyResponse(VacancyBaseResponse):
    """Полная схема анализа вакансии для ответа"""

    prompt_template: str | None = Field(description="Шаблон Промпта")
    custom_prompt: str | None = Field(description="Кастомный промпт от пользователя")
    result_data: dict | None = Field(description="анализа в формате JSON")
    result_text: str | None = Field(description="Текстовый результат анализа")
    model_used: str | None = Field(description="Какая модель LLM использовалась для анализа")
    tokens_used: int | None = Field(description="Количество использованных токенов")
    updated_at: datetime = Field(description="Дата обновления")


class VacancyListResponse(BaseModel):
    """Схема списка анализов для ответа"""

    items: list[VacancyBaseResponse] = Field(..., description="Список анализов")
    analyses_types: list[AnalysisType] = Field(..., description="Какие типы анализов сделаны")


class AnalysisTypeInfo(BaseModel):
    """Информация о типе анализа"""

    value: str = Field(description="Значение enum для API")
    display_name: str = Field(description="Отображаемое название")
    description: str = Field(description="Описание типа анализа")
    is_builtin: bool = Field(description="Является ли встроенным типом")


class AvailableAnalysesResponse(BaseModel):
    """Список доступных типов анализов"""

    items: list[AnalysisTypeInfo] = Field(description="Доступные типы анализов")
