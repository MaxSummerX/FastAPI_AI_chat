"""
Admin API для обслуживания системы памяти (mem0 + Qdrant).
"""

from fastapi import APIRouter, Depends, Query

from app.application.schemas.memory_admin import OrphanCleanupResponse
from app.application.services.orphan_cleanup_service import OrphanCleanupService
from app.presentation.dependencies import get_current_admin_user, get_orphan_cleanup_service


router = APIRouter(prefix="/memory", tags=["Admin_Memory"])


@router.post("/orphans/cleanup")
async def clean_orphans_vectors(
    dry_run: bool = Query(True, description="True - только отчёт, без удаления"),
    _: None = Depends(get_current_admin_user),
    service: OrphanCleanupService = Depends(get_orphan_cleanup_service),
) -> OrphanCleanupResponse:
    """Сверка Qdrant с PG по mem0_id; удаление векторов-сирот (по умолчанию dry_run)."""
    return await service.cleanup_orphans(dry_run=dry_run)
