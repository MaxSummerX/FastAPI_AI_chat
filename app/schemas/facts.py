from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.facts import FactCategory, FactSource


class FactBase(BaseModel):
    """Базовая схема с общей валидацией"""

    @field_validator("content", mode="before", check_fields=False)
    @classmethod
    def content_not_empty(cls, content: str | None) -> str | None:
        if content is not None and isinstance(content, str):
            stripped = content.strip()
            if not stripped:
                raise ValueError("The content of a fact cannot be empty.")
            return stripped
        return content


class FactCreate(FactBase):
    """
    Схема для создания факта пользователем вручную
    """

    content: str = Field(..., min_length=5, max_length=1000, description="Факт о пользователе")
    category: FactCategory | None = Field(default=None, description="Категория факта")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Уровень уверенности в факте (0.0-1.0)")
    metadata_: dict | None = Field(default=None, description="Дополнительные метаданные факта")


class FactUpdate(FactBase):
    """Схема для обновления существующего факта"""

    content: str | None = Field(default=None, min_length=5, max_length=1000, description="Факт о пользователе")
    category: FactCategory | None = Field(default=None, description="Категория факта")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="Уровень уверенности в факте(0.0-1.0)")
    metadata_: dict | None = Field(default=None, description="Дополнительные метаданные факта")


class FactResponse(BaseModel):
    """Схема для возврата факта клиенту"""

    id: UUID = Field(description="UUID пользователя")
    user_id: UUID = Field(description="UUID пользователя")
    content: str = Field(description="Факт о пользователе")
    category: FactCategory = Field(description="Категория факта")
    source_type: FactSource = Field(description="Источник факта")
    confidence: float = Field(description="Confidence score от LLM")
    is_active: bool = Field(description="Актуальность факта")
    superseded_by_id: UUID | None = Field(default=None, description="Каким фактом был заменён")
    created_at: datetime = Field(description="Дата создания")
    last_confirmed_at: datetime = Field(description="Последнее подтверждение факта")
    metadata_: dict | None = Field(default=None, description="Дополнительные метаданные факта")

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class FactListResponse(BaseModel):
    """Схема для списка фактов"""

    facts: list[FactResponse] = Field(..., description="Список фактов")
    total: int = Field(..., description="Общее количество фактов")
    page: int = Field(..., description="Номер страницы")
    size: int = Field(..., description="Размер страницы")
