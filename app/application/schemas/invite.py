from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InviteCodeResponse(BaseModel):
    """
    Ответ с информацией об инвайт-коде.

    Возвращается при генерации или получении списка инвайтов.
    """

    id: UUID = Field(description="UUID инвайта")
    code: str = Field(description="Инвайт-код")
    is_used: bool = Field(description="Флаг использования")
    created_at: datetime = Field(description="Дата создания")

    model_config = ConfigDict(from_attributes=True)


class InviteListResponse(BaseModel):
    """
    Ответ со списком инвайт-кодов.

    Возвращается при получении списка или генерации инвайтов.
    """

    codes: list[InviteCodeResponse] = Field(description="Список инвайт-кодов")
    count: int = Field(description="Общее количество инвайтов")


class InviteDeleteResponse(BaseModel):
    """
    Ответ при удалении инвайт-кодов.

    Возвращается при удалении неиспользованных инвайтов.
    """

    deleted_count: int = Field(description="Количество удалённых инвайтов")
