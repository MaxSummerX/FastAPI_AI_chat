"""
Юнит-тесты OrphanCleanupService (application слой).
"""

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.application.services.orphan_cleanup_service import OrphanCleanupService


class FakeFactRepo:
    """Фейк репозитория фактов: отдаёт заданное множество mem0_id."""

    def __init__(self, mem0_ids: set[UUID]) -> None:
        self._ids = mem0_ids

    async def get_all_mem0_ids(self) -> set[UUID]:
        return self._ids


class FakeScanner:
    """Фейк сканера Qdrant: отдаёт заданное множество id точек."""

    def __init__(self, point_ids: set[UUID]) -> None:
        self._ids = point_ids

    async def get_all_points_ids(self) -> set[UUID]:
        return self._ids


class FakeMemory:
    """Фейк сервиса памяти: запоминает удаления, падает на заданных id."""

    def __init__(self, fail_on: set[str] | None = None) -> None:
        self.deleted: list[str] = []
        self.fail_on = fail_on or set()

    async def delete(self, memory_id: str) -> dict[str, Any]:
        if memory_id in self.fail_on:
            raise RuntimeError("boom")
        self.deleted.append(memory_id)
        return {"status": "ok"}


def _make_service(
    pg_ids: set[UUID],
    qdrant_ids: set[UUID],
    fail_on: set[str] | None = None,
) -> tuple[OrphanCleanupService, FakeMemory]:
    """Собрать сервис на фейках и вернуть (сервис, фейк памяти)."""
    memory = FakeMemory(fail_on=fail_on)
    # Фейки структурно совместимы с интерфейсами (duck typing), но не наследуют ABC
    service = OrphanCleanupService(
        fact_repo=FakeFactRepo(pg_ids),  # type: ignore[arg-type]
        memory_service=memory,  # type: ignore[arg-type]
        scanner=FakeScanner(qdrant_ids),  # type: ignore[arg-type]
    )
    return service, memory


# ============================================================
# Сверка Qdrant <-> PG
# ============================================================


@pytest.mark.asyncio
async def test_no_orphans_when_sets_equal() -> None:
    """Тест: Qdrant и PG совпадают — сирот нет"""
    ids = {uuid4(), uuid4()}
    service, memory = _make_service(pg_ids=ids, qdrant_ids=ids)

    report = await service.cleanup_orphans(dry_run=False)

    assert report.total_qdrant == 2
    assert report.total_pg == 2
    assert report.orphans_found == 0
    assert report.deleted == 0
    assert memory.deleted == []


@pytest.mark.asyncio
async def test_orphans_are_qdrant_minus_pg() -> None:
    """Тест: сироты — точки Qdrant без пары в PG"""
    kept, orphan = uuid4(), uuid4()
    service, _ = _make_service(pg_ids={kept}, qdrant_ids={kept, orphan})

    report = await service.cleanup_orphans(dry_run=True)

    assert report.orphans_found == 1
    assert report.orphan_ids == [str(orphan)]


# ============================================================
# dry_run
# ============================================================


@pytest.mark.asyncio
async def test_dry_run_reports_without_deletion() -> None:
    """Тест: dry_run=True находит сирот, но ничего не удаляет"""
    kept, orphan = uuid4(), uuid4()
    service, memory = _make_service(pg_ids={kept}, qdrant_ids={kept, orphan})

    report = await service.cleanup_orphans(dry_run=True)

    assert report.orphans_found == 1
    assert report.deleted == 0
    assert memory.deleted == []


# ============================================================
# Удаление
# ============================================================


@pytest.mark.asyncio
async def test_deletes_only_orphans() -> None:
    """Тест: dry_run=False удаляет сирот, факты в PG не трогает"""
    kept, orphan = uuid4(), uuid4()
    service, memory = _make_service(pg_ids={kept}, qdrant_ids={kept, orphan})

    report = await service.cleanup_orphans(dry_run=False)

    assert report.deleted == 1
    assert report.failed == 0
    assert memory.deleted == [str(orphan)]


@pytest.mark.asyncio
async def test_failed_delete_does_not_stop_cleanup() -> None:
    """Тест: одна упавшая сирота не прерывает подчистку — фиксируется в failed"""
    orphan_ok, orphan_bad = uuid4(), uuid4()
    service, memory = _make_service(
        pg_ids=set(),
        qdrant_ids={orphan_ok, orphan_bad},
        fail_on={str(orphan_bad)},
    )

    report = await service.cleanup_orphans(dry_run=False)

    assert report.orphans_found == 2
    assert report.deleted == 1
    assert report.failed == 1
    assert memory.deleted == [str(orphan_ok)]
