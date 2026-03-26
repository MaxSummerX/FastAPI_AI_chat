import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PromptBase(BaseModel):
    """Базовая схема промпта"""

    title: str | None = Field(None, max_length=255, description="Название промпта")
    content: str = Field(..., min_length=1, description="Содержание промпта")
    metadata_: dict[str, Any] | None = Field(None, description="Метаданные промпта")


class PromptCreate(PromptBase):
    """Схема для создания промпта"""

    pass


class PromptUpdate(BaseModel):
    """Схема для обновления промпта"""

    title: str | None = Field(None, max_length=255, description="Новое название промпта")
    content: str | None = Field(None, min_length=1, description="Новое содержание промпта")
    metadata_: dict[str, Any] | None = Field(None, description="Новые метаданные промпта")
    is_active: bool | None = Field(None, description="Статус промпта")


class PromptResponseBase(PromptBase):
    """Базовая схема ответа с промптом"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="ID промпта")
    user_id: uuid.UUID = Field(..., description="ID владельца промпта")
    is_active: bool = Field(..., description="Активен ли промпт")
    created_at: datetime = Field(..., description="Время создания")
    updated_at: datetime = Field(..., description="Время обновления")


class PromptResponse(PromptResponseBase):
    """Полная схема ответа с промптом"""

    pass


class PromptListResponse(BaseModel):
    """Схема для списка промптов"""

    prompts: list[PromptResponseBase] = Field(..., description="Список промптов")
    total: int = Field(..., description="Общее количество промптов")
    page: int = Field(..., description="Номер страницы")
    size: int = Field(..., description="Размер страницы")
