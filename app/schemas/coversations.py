from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    """
    Схема для создания новой беседы.
    Используется в POST-запросах.
    """

    title: str | None = Field(None, min_length=3, max_length=50, description="Название беседы")


class ConversationResponse(BaseModel):
    """
    Схема для ответа с основными данными беседы.
    Используется в POST-запросах.
    """

    id: UUID = Field(description="UUID беседы")
    user_id: UUID = Field(description="UUID пользователя")
    title: str | None = Field(None, description="Название беседы")
    created_at: datetime = Field(description="Дата создания")

    model_config = ConfigDict(from_attributes=True)
