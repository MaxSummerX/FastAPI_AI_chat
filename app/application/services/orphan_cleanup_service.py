"""
Сервис фоновой подчистки векторов-сирот в Qdrant.
"""

from uuid import UUID

from loguru import logger

from app.application.schemas.memory_admin import OrphanCleanupResponse
from app.domain.repositories.facts import IFactRepository
from app.domain.services.memory import IMemoryService
from app.infrastructure.memory.scanner import QdrantPointScanner


class OrphanCleanupService:
    """
    Сверка Qdrant с PG и удаление векторов-сирот.
    """

    def __init__(
        self,
        fact_repo: IFactRepository,
        memory_service: IMemoryService,
        scanner: QdrantPointScanner,
    ) -> None:
        """
        Инициализирует сервис.

        Args:
            fact_repo: Репозиторий фактов PG
            memory_service: Сервис памяти (mem0) для удаления сирот
            scanner: Сканер точек Qdrant
        """
        self.fact_repo = fact_repo
        self.memory_service = memory_service
        self.scanner = scanner

    async def cleanup_orphans(self, dry_run: bool = True) -> OrphanCleanupResponse:
        """
        Найти и (если не dry_run) удалить точки Qdrant, отсутствующие в PG.

        Одна неудачная сирота не прерывает подчистку - фиксируется в отчёте.

        Args:
            dry_run: True - только отчёт, ничего не удалять

        Returns:
            Отчёт со статистикой сверки и удаления.
        """
        pg_ids: set[UUID] = await self.fact_repo.get_all_mem0_ids()
        qdrant_ids: set[UUID] = await self.scanner.get_all_points_ids()

        orphan_ids = qdrant_ids - pg_ids
        logger.info("Сверка Qdrant <-> PG: qdrant={}, pg={}, сирот={}", len(qdrant_ids), len(pg_ids), len(orphan_ids))

        deleted = failed = 0
        if not dry_run:
            for mem0_id in orphan_ids:
                try:
                    # delete чистит Qdrant + Neo4j + history одним вызовом
                    await self.memory_service.delete(memory_id=str(mem0_id))
                    deleted += 1
                except Exception as e:
                    failed += 1
                    logger.error("Не удалось удалить вектор-сироту {}: {}", mem0_id, e)

        return OrphanCleanupResponse(
            total_qdrant=len(qdrant_ids),
            total_pg=len(pg_ids),
            orphans_found=len(orphan_ids),
            deleted=deleted,
            failed=failed,
            orphan_ids=sorted(str(i) for i in orphan_ids),
        )
