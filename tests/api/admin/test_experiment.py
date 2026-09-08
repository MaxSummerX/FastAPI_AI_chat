"""
Тесты для experiment endpoints admin API (presentation слой).

Эндпоинт: PATCH /api/admin/experiment/sync-archive — фоновая синхронизация
статусов архивации вакансий. Фоновая обёртка подменяется патчем в модуле роутера.
"""

from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_sync_archive_unauthorized(client: AsyncClient) -> None:
    """Тест: синхронизация без авторизации"""
    response = await client.patch("/api/admin/experiment/sync-archive")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_sync_archive_forbidden(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: синхронизация обычным пользователем (должно быть запрещено)"""
    response = await client.patch("/api/admin/experiment/sync-archive", headers=auth_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_sync_archive_success(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    """Тест: успешный запуск — 200, фоновая обёртка замокана (реальной синхронизации нет)"""
    with patch("app.presentation.routers.admin.experiment.bg_sync_archive_statuses"):
        response = await client.patch("/api/admin/experiment/sync-archive", headers=admin_headers)
    assert response.status_code == 200
