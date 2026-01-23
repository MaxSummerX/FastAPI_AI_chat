from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class InviteCodeResponse(BaseModel):
    """Ответ с информацией об инвайт-коде"""

    id: UUID
    code: str
    created_at: datetime


class InviteCreateResponse(BaseModel):
    """Ответ при генерации инвайт-кодов"""

    codes: list[str]
    count: int


class InviteListResponse(BaseModel):
    """Ответ со списком инвайт-кодов"""

    codes: list[InviteCodeResponse]
    count: int
