"""
Тесты для memory endpoints admin API (presentation слой).

Эндпоинт (требует роль ADMIN):
- POST /api/admin/memory/orphans/cleanup — сверка Qdrant с PG по mem0_id,
  удаление векторов-сирот (dry_run по умолчанию)

Сервис подчистки подменяется заглушкой через dependency_overrides —
реальный Qdrant в тестах не нужен.
"""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.application.schemas.memory_admin import OrphanCleanupResponse
from app.presentation.dependencies import get_orphan_cleanup_service


class StubCleanupService:
    """Заглушка OrphanCleanupService: возвращает предзаданный отчёт, запоминает dry_run."""

    def __init__(self) -> None:
        self.called_with: list[bool] = []

    async def cleanup_orphans(self, dry_run: bool = True) -> OrphanCleanupResponse:
        self.called_with.append(dry_run)
        return OrphanCleanupResponse(
            total_qdrant=10,
            total_pg=8,
            orphans_found=2,
            deleted=0 if dry_run else 2,
            failed=0,
            orphan_ids=[str(uuid4()), str(uuid4())],
        )


@pytest.fixture
def stub_cleanup_service() -> StubCleanupService:
    return StubCleanupService()


@pytest.fixture
async def client_with_stub_cleanup(
    client: AsyncClient, stub_cleanup_service: StubCleanupService
) -> AsyncGenerator[AsyncClient]:
    """
    HTTP клиент с подменённым сервисом подчистки сирот.

    Override накатывается поверх стандартного client (который уже
    подменяет get_db и get_memory) и снимается после теста.
    """
    from app.main import app

    app.dependency_overrides[get_orphan_cleanup_service] = lambda: stub_cleanup_service
    yield client
    app.dependency_overrides.pop(get_orphan_cleanup_service, None)


# ============================================================
# POST /memory/orphans/cleanup - права доступа
# ============================================================


@pytest.mark.asyncio
async def test_cleanup_unauthorized(client: AsyncClient) -> None:
    """Тест: подчистка без авторизации"""
    response = await client.post("/api/admin/memory/orphans/cleanup")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_cleanup_forbidden(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: подчистка обычным пользователем (должно быть запрещено)"""
    response = await client.post("/api/admin/memory/orphans/cleanup", headers=auth_headers)
    assert response.status_code == 403


# ============================================================
# POST /memory/orphans/cleanup - отчёт
# ============================================================


@pytest.mark.asyncio
async def test_cleanup_dry_run_by_default(
    client_with_stub_cleanup: AsyncClient,
    admin_headers: dict[str, str],
    stub_cleanup_service: StubCleanupService,
) -> None:
    """Тест: без параметра — dry_run, отчёт без удалений"""
    response = await client_with_stub_cleanup.post("/api/admin/memory/orphans/cleanup", headers=admin_headers)

    assert response.status_code == 200
    assert stub_cleanup_service.called_with == [True]

    data = response.json()
    assert data["total_qdrant"] == 10
    assert data["total_pg"] == 8
    assert data["orphans_found"] == 2
    assert data["deleted"] == 0
    assert len(data["orphan_ids"]) == 2


@pytest.mark.asyncio
async def test_cleanup_actual_run(
    client_with_stub_cleanup: AsyncClient,
    admin_headers: dict[str, str],
    stub_cleanup_service: StubCleanupService,
) -> None:
    """Тест: dry_run=false — сервис вызван с False, удаления отражены в отчёте"""
    response = await client_with_stub_cleanup.post(
        "/api/admin/memory/orphans/cleanup?dry_run=false", headers=admin_headers
    )

    assert response.status_code == 200
    assert stub_cleanup_service.called_with == [False]
    assert response.json()["deleted"] == 2
