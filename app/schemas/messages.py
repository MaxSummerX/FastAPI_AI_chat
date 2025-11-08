from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MessageCreate(BaseModel):
    """
    Схема для создания нового сообщения в беседе.
    Используется в POST-запросах.
    """

    role: str = Field(
        default="user", pattern="^(user|assistant|system)$", description="Роль: 'user', 'assistant' или 'system'"
    )
    content: str = Field(description="Сообщение")


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
