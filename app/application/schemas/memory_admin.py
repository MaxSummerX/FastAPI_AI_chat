"""
Схемы ответов Admin API для обслуживания системы памяти.
"""

from pydantic import BaseModel, Field


class OrphanCleanupResponse(BaseModel):
    """Отчёт о сверке Qdrant <-> PG по mem0_id."""

    total_qdrant: int = Field(description="Всего точек в коллекции Qdrant")
    total_pg: int = Field(description="Всего mem0_id в PG")
    orphans_found: int = Field(description="Найдено векторов-сирот")
    deleted: int = Field(description="Удалено (0 при dry_run)")
    failed: int = Field(description="Не удалось удалить")
    orphan_ids: list[str] = Field(description="id сирот")
