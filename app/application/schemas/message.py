from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MessageCreate(BaseModel):
    """
    Схема для создания нового сообщения в беседе.
    Используется в POST-запросах.
    """

    role: str = Field(
        default="user", pattern="^(user|assistant|system)$", description="Роль: 'user', 'assistant' или 'system'"
    )
    content: str = Field(min_length=1, description="Сообщение")

    @field_validator("content")
    @classmethod
    def content_must_not_be_empty(cls, v: str) -> str:
        """Валидация что контент не пустой или только из пробелов."""
        if not v or not v.strip():
            raise ValueError("Message content cannot be empty")
        return v


class MessageResponse(BaseModel):
    """
    Схема для ответа с данными сообщения из беседы.
    Используется в POST и GET-запросах.
    """

    id: UUID = Field(description="UUID сообщения")
    role: str = Field(description="Роль")
    content: str = Field(description="Сообщение")
    timestamp: datetime = Field(description="Временная метка")

    model_config = ConfigDict(from_attributes=True)


class HistoryMessage(BaseModel):
    """
    Схема для LLM с автоматическим извлечением значений Enum
    """

    role: str = Field(description="Роль")
    content: str = Field(description="Сообщение")

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class MessageStreamRequest(BaseModel):
    """
    Схема запроса для создания сообщения с поточным ответом.
    """

    message: MessageCreate = Field(description="Сообщение пользователя")
    mem0ai_on: bool = Field(default=False, description="Использовать mem0ai для извлечения и поиска релевантных фактов")
    mem0ai_save: bool = Field(default=True, description="")
    prompt_id: UUID | None = Field(default=None, description="ID кастомного промпта (опционально)")
    model: str | None = Field(
        default=None, description="Название модели LLM (опционально, используется модель по умолчанию)"
    )
    sliding_window: int = Field(
        default=10, ge=1, le=1000, description="Количество сообщений для контекста LLM (sliding window)"
    )
    memory_facts: int = Field(
        default=5, ge=1, le=100, description="Количество релевантных фактов из памяти для добавления в контекст"
    )
