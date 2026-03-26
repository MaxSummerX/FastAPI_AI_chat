from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    """
    Схема для создания новой беседы.
    Используется в POST-запросах.
    """

    title: str | None = Field(None, min_length=3, max_length=50, description="Название беседы")


class ConversationUpdate(BaseModel):
    """
    Схема для обновления беседы.
    Используется в PATCH-запросах.
    """

    title: str | None = Field(None, description="Название беседы")
    is_archived: bool = Field(False, description="Архивная беседа")


class ConversationResponse(BaseModel):
    """
    Схема для ответа с основными данными беседы.
    Используется в POST-запросах.
    """

    id: UUID = Field(description="UUID беседы")
    user_id: UUID = Field(description="UUID пользователя")
    title: str | None = Field(None, description="Название беседы")
    created_at: datetime = Field(description="Дата создания")
    updated_at: datetime | None = Field(None, description="Дата обновления")
    is_archived: bool = Field(default=False, description="Архивная ли беседа")

    model_config = ConfigDict(from_attributes=True)
