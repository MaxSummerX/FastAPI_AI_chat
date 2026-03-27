"""
Тесты для invite endpoints admin API (presentation слой).

Эндпоинты (все требуют роль ADMIN):
- POST   /api/admin/invites         — генерация инвайт-кодов
- GET    /api/admin/invites/unused   — список неиспользованных кодов с пагинацией
- DELETE /api/admin/invites/unused   — удаление всех неиспользованных кодов

Архитектура: Presentation (router) → Application (InviteService) → Domain (IInviteRepository) → Infrastructure (InviteSQLAlchemyRepository)
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.invite import Invite as InviteModel


# ============================================================
# POST /invites - генерация инвайт-кодов
# ============================================================


@pytest.mark.asyncio
async def test_generate_invite_codes_unauthorized(client: AsyncClient) -> None:
    """Тест: генерация кодов без авторизации"""
    response = await client.post("/api/admin/invites?count=5")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_generate_invite_codes_forbidden(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: генерация кодов обычным пользователем (должно быть запрещено)"""
    response = await client.post("/api/admin/invites?count=5", headers=auth_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_generate_invite_codes_success(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """Тест: успешная генерация инвайт-кодов"""
    response = await client.post("/api/admin/invites?count=3", headers=admin_headers)
    assert response.status_code == 201

    data = response.json()
    assert "codes" in data
    assert "count" in data
    assert len(data["codes"]) == 3
    assert data["count"] == 3

    # Проверяем что коды сохранены в БД
    from app.domain.models.invite import Invite

    codes_list = [item["code"] for item in data["codes"]]
    result = await db_session.scalars(select(Invite).where(Invite.code.in_(codes_list)))
    invites = result.all()
    assert len(invites) == 3

    # Проверяем что коды не использованы
    for invite in invites:
        assert invite.is_used is False
        assert invite.used_by_user_id is None
        assert invite.used_at is None


@pytest.mark.asyncio
async def test_generate_invite_codes_invalid_count(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    """Тест: генерация с невалидным количеством"""
    # Отрицательное число
    response = await client.post("/api/admin/invites?count=-1", headers=admin_headers)
    assert response.status_code == 422

    # Ноль
    response = await client.post("/api/admin/invites?count=0", headers=admin_headers)
    assert response.status_code == 422

    # Слишком большое число
    response = await client.post("/api/admin/invites?count=101", headers=admin_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_generate_invite_codes_default_count(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    """Тест: генерация с количеством по умолчанию"""
    response = await client.post("/api/admin/invites", headers=admin_headers)
    assert response.status_code == 201

    data = response.json()
    # Default count = 1
    assert data["count"] == 1
    assert len(data["codes"]) == 1


@pytest.mark.asyncio
async def test_generate_invite_codes_unique(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    """Тест: сгенерированные коды уникальны"""
    response = await client.post("/api/admin/invites?count=10", headers=admin_headers)
    assert response.status_code == 201

    data = response.json()
    codes = data["codes"]
    assert len(codes) == len({item["code"] for item in data["codes"]})


# ============================================================
# GET /invites/unused - получение списка неиспользованных кодов
# ============================================================


@pytest.mark.asyncio
async def test_get_unused_invites_unauthorized(client: AsyncClient) -> None:
    """Тест: получение кодов без авторизации"""
    response = await client.get("/api/admin/invites/unused")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_unused_invites_forbidden(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: получение кодов обычным пользователем (должно быть запрещено)"""
    response = await client.get("/api/admin/invites/unused", headers=auth_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_unused_invites_success(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    """Тест: успешное получение списка неиспользованных кодов"""
    response = await client.get("/api/admin/invites/unused", headers=admin_headers)
    assert response.status_code == 200

    data = response.json()
    assert "codes" in data
    assert "count" in data

    # Только неиспользованные коды
    for item in data["codes"]:
        assert item["is_used"] is False


@pytest.mark.asyncio
async def test_get_unused_invites_empty(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """Тест: список пуст когда все коды использованы"""
    from datetime import UTC, datetime, timedelta

    from app.domain.models.invite import Invite

    invite = Invite(
        id=uuid.uuid4(),
        code="used_code",
        is_used=True,
        used_by_user_id=uuid.uuid4(),
        created_at=datetime.now(UTC) - timedelta(days=1),
        used_at=datetime.now(UTC),
    )
    db_session.add(invite)
    await db_session.commit()

    response = await client.get("/api/admin/invites/unused", headers=admin_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["count"] == 0
    assert len(data["codes"]) == 0


@pytest.mark.asyncio
async def test_get_unused_invites_structure(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    """Тест: проверка структуры ответа"""
    response = await client.get("/api/admin/invites/unused", headers=admin_headers)
    assert response.status_code == 200

    data = response.json()
    if len(data["codes"]) > 0:
        item = data["codes"][0]
        # Проверяем наличие всех полей
        assert "id" in item
        assert "code" in item
        assert "is_used" in item
        assert "created_at" in item


# ============================================================
# DELETE /invites/unused - удаление всех неиспользованных кодов
# ============================================================


@pytest.mark.asyncio
async def test_delete_invite_code_unauthorized(client: AsyncClient) -> None:
    """Тест: удаление кодов без авторизации"""
    response = await client.delete("/api/admin/invites/unused")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_invite_code_forbidden(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: удаление кодов обычным пользователем (должно быть запрещено)"""
    response = await client.delete("/api/admin/invites/unused", headers=auth_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_invite_code_success(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession, test_invite: InviteModel
) -> None:
    """Тест: успешное удаление кода"""
    code = test_invite.code

    response = await client.delete("/api/admin/invites/unused", headers=admin_headers)
    assert response.status_code == 200

    # Проверяем что код удалён из БД
    from app.domain.models.invite import Invite

    result = await db_session.scalars(select(Invite).where(Invite.code == code))
    invite = result.first()
    assert invite is None


# ============================================================
# Пагинация и интеграционные тесты
# ============================================================


@pytest.mark.asyncio
async def test_unused_pagination(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    """Тест: проверка пагинации списка"""

    # Генерируем больше чем лимит
    response = await client.post("/api/admin/invites?count=10", headers=admin_headers)
    assert response.status_code == 201
    codes_batch_1 = [item["code"] for item in response.json()["codes"]]
    assert len(codes_batch_1) == 10

    response = await client.post("/api/admin/invites?count=10", headers=admin_headers)
    assert response.status_code == 201
    codes_batch_2 = [item["code"] for item in response.json()["codes"]]
    assert len(codes_batch_2) == 10

    all_codes = codes_batch_1 + codes_batch_2
    assert len(all_codes) == 20
    assert len(set(all_codes)) == 20

    # Получаем первую страницу
    response = await client.get("/api/admin/invites/unused?skip=0&limit=10", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["codes"]) == 10
    assert data["count"] == 20

    # Получаем вторую страницу
    response = await client.get("/api/admin/invites/unused?skip=10&limit=10", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["codes"]) == 10

    # Получаем третью страницу (пустая)
    response = await client.get("/api/admin/invites/unused?skip=20&limit=10", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["codes"]) == 0


@pytest.mark.asyncio
async def test_full_invite_workflow(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    """Тест: генерация → проверка в списке → удаление"""

    # 1. Генерируем коды
    response = await client.post("/api/admin/invites?count=5", headers=admin_headers)
    assert response.status_code == 201
    codes = [item["code"] for item in response.json()["codes"]]
    assert len(codes) == 5

    # 2. Проверяем что коды в списке неиспользованных
    response = await client.get("/api/admin/invites/unused", headers=admin_headers)
    assert response.status_code == 200
    unused_codes = [item["code"] for item in response.json()["codes"]]
    assert all(code in unused_codes for code in codes)

    # 3. Удаляем все неиспользованные
    response = await client.delete("/api/admin/invites/unused", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["deleted_count"] >= 5

    # 4. Проверяем что список пуст
    response = await client.get("/api/admin/invites/unused", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["count"] == 0


@pytest.mark.asyncio
async def test_delete_unused_when_empty(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    """Тест: удаление когда нет неиспользованных кодов"""

    response = await client.delete("/api/admin/invites/unused", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["deleted_count"] == 0
