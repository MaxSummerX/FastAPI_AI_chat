from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums.document import DocumentCategory


class DocumentBase(BaseModel):
    """Базовая схема с общей валидацией"""

    @field_validator("content", mode="before", check_fields=False)
    @classmethod
    def content_not_empty(cls, content: str | None) -> str | None:
        if content is not None and isinstance(content, str):
            stripped = content.strip()
            if not stripped:
                raise ValueError("The content of a document cannot be empty.")
            return stripped
        return content


class DocumentCreate(DocumentBase):
    """Схема для создания документа пользователем вручную"""

    title: str | None = Field(default=None, max_length=255, description="Название документа")
    content: str = Field(..., min_length=5, max_length=20000, description="Содержимое документа (основной текст)")
    category: DocumentCategory | None = Field(default=None, description="Категория документа")
    metadata_: dict | None = Field(default=None, description="Произвольные метаданные в формате JSON")
    tags: list[str] | None = Field(default=None, description="Тэги для организации и поиска документов")


class DocumentUpdate(DocumentBase):
    """Схема для частичного обновления документа"""

    title: str | None = Field(default=None, max_length=255, description="Название документа")
    content: str | None = Field(
        default=None, min_length=5, max_length=20000, description="Содержимое документа (основной текст)"
    )
    category: DocumentCategory | None = Field(default=None, description="Категория документа")
    metadata_: dict | None = Field(default=None, description="Произвольные метаданные в формате JSON")
    tags: list[str] | None = Field(default=None, description="Тэги для организации и поиска документов")
    is_archived: bool | None = Field(default=None, description="Архивирован ли документ (мягкое удаление)")


class DocumentResponse(BaseModel):
    """Схема для возврата документа клиенту"""

    id: UUID = Field(description="UUID документа")
    title: str | None = Field(description="Название документа")
    user_id: UUID = Field(description="UUID владельца документа")
    content: str = Field(description="Содержимое документа (основной текст)")
    category: DocumentCategory = Field(description="Категория документа")
    is_archived: bool = Field(description="Архивирован ли документ (мягкое удаление)")
    created_at: datetime = Field(description="Дата создания документа")
    updated_at: datetime = Field(description="Дата последнего обновления")
    metadata_: dict | None = Field(default=None, description="Произвольные метаданные в формате JSON")
    tags: list[str] | None = Field(default=None, description="Тэги для организации и поиска документов")
    summary: str | None = Field(default=None, description="Краткое описание/саммари документа (генерируется AI)")
    conversation_id: UUID | None = Field(default=None, description="ID связанной беседы (источник документа)")
    message_id: UUID | None = Field(default=None, description="ID связанного сообщения (источник документа)")

    model_config = ConfigDict(from_attributes=True, use_enum_values=True, populate_by_name=True)


class BaseResponse(BaseModel):
    """Базовая схема ответа с основными полями документа"""

    id: UUID = Field(description="UUID документа")
    title: str | None = Field(description="Название документа")
    category: DocumentCategory = Field(description="Категория документа")
    created_at: datetime = Field(description="Дата создания документа")
    updated_at: datetime = Field(description="Дата последнего обновления")
    metadata_: dict | None = Field(default=None, description="Произвольные метаданные в формате JSON")
    tags: list[str] | None = Field(default=None, description="Тэги для организации и поиска документов")
    summary: str | None = Field(default=None, description="Краткое описание/саммари документа (генерируется AI)")

    model_config = ConfigDict(from_attributes=True, use_enum_values=True, populate_by_name=True)


class DocumentSearchResult(BaseResponse):
    """Результат поиска документов с метрикой релевантности"""

    relevance_score: float = Field(description="Оценка релевантности (0.0 - 1.0)")


class DocumentSearchResponse(BaseModel):
    """Результаты поиска документов"""

    documents: list[DocumentSearchResult] = Field(..., description="Список документов")
    query: str = Field(..., description="Поисковый запрос")
    limit: int = Field(..., description="Максимальное количество результатов")
    offset: int = Field(..., description="Смещение для пагинации")
