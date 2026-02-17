from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.enum.documents import DocumentCategory


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
    metadata_: dict | None = Field(default=None, alias="metadata", description="Произвольные метаданные в формате JSON")
    tags: list[str] | None = Field(default=None, description="Тэги для организации и поиска документов")


class DocumentUpdate(DocumentBase):
    """Схема для частичного обновления документа"""

    title: str | None = Field(default=None, max_length=255, description="Название документа")
    content: str | None = Field(
        default=None, min_length=5, max_length=20000, description="Содержимое документа (основной текст)"
    )
    category: DocumentCategory | None = Field(default=None, description="Категория документа")
    metadata_: dict | None = Field(default=None, alias="metadata", description="Произвольные метаданные в формате JSON")
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
    metadata_: dict | None = Field(alias="metadata", description="Произвольные метаданные в формате JSON")
    tags: list[str] | None = Field(description="Тэги для организации и поиска документов")
    summary: str | None = Field(description="Краткое описание/саммари документа (генерируется AI)")
    conversation_id: UUID | None = Field(description="ID связанной беседы (источник документа)")
    message_id: UUID | None = Field(description="ID связанного сообщения (источник документа)")

    model_config = ConfigDict(from_attributes=True, use_enum_values=True, populate_by_name=True)


class DocumentListResponse(BaseModel):
    """Схема для списка документов"""

    documents: list[DocumentResponse] = Field(..., description="Список документов")
    total: int = Field(..., description="Общее количество документов")
    page: int = Field(..., description="Номер страницы")
    size: int = Field(..., description="Размер страницы")
