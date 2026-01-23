"""
Тесты для invite endpoints API v2.

Покрывает все основные сценарии:
- Генерация инвайт-кодов (admin only)
- Получение списка неиспользованных кодов (admin only)
- Проверка кода (требует авторизации)
- Использование кода
- Удаление кода (admin only)
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Invite as InviteModel


# ============================================================
# POST /invites - генерация инвайт-кодов
# ============================================================


@pytest.mark.asyncio
async def test_generate_invite_codes_unauthorized(client: AsyncClient) -> None:
    """Тест: генерация кодов без авторизации"""
    response = await client.post("/api/v2/invites?count=5")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_generate_invite_codes_forbidden(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: генерация кодов обычным пользователем (должно быть запрещено)"""
    response = await client.post("/api/v2/invites?count=5", headers=auth_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_generate_invite_codes_success(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """Тест: успешная генерация инвайт-кодов"""
    response = await client.post("/api/v2/invites?count=3", headers=admin_headers)
    assert response.status_code == 201

    data = response.json()
    assert "codes" in data
    assert "count" in data
    assert len(data["codes"]) == 3
    assert data["count"] == 3

    # Проверяем что коды сохранены в БД
    from app.models.invites import Invite

    result = await db_session.scalars(select(Invite).where(Invite.code.in_(data["codes"])))
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
    response = await client.post("/api/v2/invites?count=-1", headers=admin_headers)
    assert response.status_code == 422

    # Ноль
    response = await client.post("/api/v2/invites?count=0", headers=admin_headers)
    assert response.status_code == 422

    # Слишком большое число
    response = await client.post("/api/v2/invites?count=101", headers=admin_headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_generate_invite_codes_default_count(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    """Тест: генерация с количеством по умолчанию"""
    response = await client.post("/api/v2/invites", headers=admin_headers)
    assert response.status_code == 201

    data = response.json()
    # Default count = 1
    assert data["count"] == 1
    assert len(data["codes"]) == 1


@pytest.mark.asyncio
async def test_generate_invite_codes_unique(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    """Тест: сгенерированные коды уникальны"""
    response = await client.post("/api/v2/invites?count=10", headers=admin_headers)
    assert response.status_code == 201

    data = response.json()
    codes = data["codes"]
    assert len(codes) == len(set(codes))  # Все коды уникальны


# ============================================================
# GET /invites/unused - получение списка неиспользованных кодов
# ============================================================


@pytest.mark.asyncio
async def test_get_unused_invites_unauthorized(client: AsyncClient) -> None:
    """Тест: получение кодов без авторизации"""
    response = await client.get("/api/v2/invites/unused")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_unused_invites_forbidden(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: получение кодов обычным пользователем (должно быть запрещено)"""
    response = await client.get("/api/v2/invites/unused", headers=auth_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_unused_invites_success(
    client: AsyncClient, admin_headers: dict[str, str], test_invites: list[InviteModel]
) -> None:
    """Тест: успешное получение списка неиспользованных кодов"""
    response = await client.get("/api/v2/invites/unused", headers=admin_headers)
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

    from app.models.invites import Invite

    # Создаём использованный код
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

    response = await client.get("/api/v2/invites/unused", headers=admin_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["count"] == 0
    assert len(data["codes"]) == 0


@pytest.mark.asyncio
async def test_get_unused_invites_structure(
    client: AsyncClient, admin_headers: dict[str, str], test_invites: list[InviteModel]
) -> None:
    """Тест: проверка структуры ответа"""
    response = await client.get("/api/v2/invites/unused", headers=admin_headers)
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
# GET /invites/{code} - проверка кода
# ============================================================


@pytest.mark.asyncio
async def test_check_invite_code_unauthorized(client: AsyncClient, test_invite: InviteModel) -> None:
    """Тест: проверка кода без авторизации"""
    response = await client.get(f"/api/v2/invites/{test_invite.code}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_check_invite_code_success(
    client: AsyncClient, auth_headers: dict[str, str], test_invite: InviteModel
) -> None:
    """Тест: успешная проверка кода"""
    response = await client.get(f"/api/v2/invites/{test_invite.code}", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert "id" in data
    assert data["code"] == test_invite.code
    assert data["is_used"] is False


@pytest.mark.asyncio
async def test_check_invite_code_used(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession, test_invite: InviteModel
) -> None:
    """Тест: проверка использованного кода"""
    from datetime import UTC, datetime

    test_invite.is_used = True
    test_invite.used_by_user_id = uuid.uuid4()
    test_invite.used_at = datetime.now(UTC)
    await db_session.commit()
    await db_session.refresh(test_invite)

    response = await client.get(f"/api/v2/invites/{test_invite.code}", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["is_used"] is True


@pytest.mark.asyncio
async def test_check_invite_code_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: проверка несуществующего кода"""
    response = await client.get("/api/v2/invites/nonexistent_code", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_check_invite_code_case_sensitive(
    client: AsyncClient, auth_headers: dict[str, str], test_invite: InviteModel
) -> None:
    """Тест: проверка чувствительности к регистру"""
    # Код в другом регистре не должен найтись
    response = await client.get(f"/api/v2/invites/{test_invite.code.upper()}", headers=auth_headers)
    assert response.status_code == 404


# ============================================================
# POST /invites/{code}/use - использование кода
# ============================================================


@pytest.mark.asyncio
async def test_use_invite_code_unauthorized(client: AsyncClient, test_invite: InviteModel) -> None:
    """Тест: использование кода без авторизации"""
    response = await client.post(f"/api/v2/invites/{test_invite.code}/use")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_use_invite_code_success(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession, test_invite: InviteModel
) -> None:
    """Тест: успешное использование кода"""
    response = await client.post(f"/api/v2/invites/{test_invite.code}/use", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert "message" in data
    assert "code" in data
    assert data["code"] == test_invite.code

    # Проверяем что код помечен как использованный
    await db_session.refresh(test_invite)
    assert test_invite.is_used is True
    assert test_invite.used_by_user_id is not None
    assert test_invite.used_at is not None


@pytest.mark.asyncio
async def test_use_invite_code_already_used(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession, test_invite: InviteModel
) -> None:
    """Тест: попытка использовать уже использованный код"""
    from datetime import UTC, datetime

    test_invite.is_used = True
    test_invite.used_by_user_id = uuid.uuid4()
    test_invite.used_at = datetime.now(UTC)
    await db_session.commit()

    response = await client.post(f"/api/v2/invites/{test_invite.code}/use", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_use_invite_code_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: использование несуществующего кода"""
    response = await client.post("/api/v2/invites/nonexistent_code/use", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_use_invite_code_idempotent(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession, test_invite: InviteModel
) -> None:
    """Тест: повторное использование того же кода тем же пользователем"""
    # Первое использование
    response1 = await client.post(f"/api/v2/invites/{test_invite.code}/use", headers=auth_headers)
    assert response1.status_code == 200

    # Второе использование - должно вернуть 404 (уже использован)
    response2 = await client.post(f"/api/v2/invites/{test_invite.code}/use", headers=auth_headers)
    assert response2.status_code == 404


# ============================================================
# DELETE /invites/{code} - удаление кода
# ============================================================


@pytest.mark.asyncio
async def test_delete_invite_code_unauthorized(client: AsyncClient, test_invite: InviteModel) -> None:
    """Тест: удаление кода без авторизации"""
    response = await client.delete(f"/api/v2/invites/{test_invite.code}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_invite_code_forbidden(
    client: AsyncClient, auth_headers: dict[str, str], test_invite: InviteModel
) -> None:
    """Тест: удаление кода обычным пользователем (должно быть запрещено)"""
    response = await client.delete(f"/api/v2/invites/{test_invite.code}", headers=auth_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_invite_code_success(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession, test_invite: InviteModel
) -> None:
    """Тест: успешное удаление кода"""
    code = test_invite.code

    response = await client.delete(f"/api/v2/invites/{code}", headers=admin_headers)
    assert response.status_code == 204

    # Проверяем что код удалён из БД
    from app.models.invites import Invite

    result = await db_session.scalars(select(Invite).where(Invite.code == code))
    invite = result.first()
    assert invite is None


@pytest.mark.asyncio
async def test_delete_invite_code_not_found(client: AsyncClient, admin_headers: dict[str, str]) -> None:
    """Тест: удаление несуществующего кода"""
    response = await client.delete("/api/v2/invites/nonexistent_code", headers=admin_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_invite_code_returns_no_content(
    client: AsyncClient, admin_headers: dict[str, str], test_invite: InviteModel
) -> None:
    """Тест: удаление возвращает 204 No Content без тела ответа"""
    response = await client.delete(f"/api/v2/invites/{test_invite.code}", headers=admin_headers)
    assert response.status_code == 204
    assert response.content == b""


@pytest.mark.asyncio
async def test_delete_used_invite_code(
    client: AsyncClient, admin_headers: dict[str, str], db_session: AsyncSession, test_invite: InviteModel
) -> None:
    """Тест: удаление использованного кода"""
    from datetime import UTC, datetime

    test_invite.is_used = True
    test_invite.used_by_user_id = uuid.uuid4()
    test_invite.used_at = datetime.now(UTC)
    await db_session.commit()

    response = await client.delete(f"/api/v2/invites/{test_invite.code}", headers=admin_headers)
    assert response.status_code == 204

    # Проверяем что код удалён
    from app.models.invites import Invite

    result = await db_session.scalars(select(Invite).where(Invite.code == test_invite.code))
    deleted_invite = result.first()
    assert deleted_invite is None


# ============================================================
# Интеграционные тесты
# ============================================================


@pytest.mark.asyncio
async def test_full_invite_workflow(
    client: AsyncClient, admin_headers: dict[str, str], auth_headers: dict[str, str]
) -> None:
    """Тест: полный цикл работы с инвайт-кодом"""
    # 1. Генерация кода (admin)
    gen_response = await client.post("/api/v2/invites?count=1", headers=admin_headers)
    assert gen_response.status_code == 201
    code = gen_response.json()["codes"][0]

    # 2. Проверка что код в списке неиспользованных
    unused_response = await client.get("/api/v2/invites/unused", headers=admin_headers)
    assert unused_response.status_code == 200
    codes = [item["code"] for item in unused_response.json()["codes"]]
    assert code in codes

    # 3. Проверка кода (требует авторизации)
    check_response = await client.get(f"/api/v2/invites/{code}", headers=auth_headers)
    assert check_response.status_code == 200
    assert check_response.json()["is_used"] is False

    # 4. Использование кода
    use_response = await client.post(f"/api/v2/invites/{code}/use", headers=auth_headers)
    assert use_response.status_code == 200
    assert "message" in use_response.json()

    # 5. Проверка что код теперь использован
    check_response2 = await client.get(f"/api/v2/invites/{code}", headers=auth_headers)
    assert check_response2.status_code == 200
    assert check_response2.json()["is_used"] is True

    # 6. Проверка что код не в списке неиспользованных
    unused_response2 = await client.get("/api/v2/invites/unused", headers=admin_headers)
    assert unused_response2.status_code == 200
    codes2 = [item["code"] for item in unused_response2.json()["codes"]]
    assert code not in codes2


@pytest.mark.asyncio
async def test_cannot_use_other_users_invite(
    client: AsyncClient, admin_headers: dict[str, str], auth_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """Тест: нельзя использовать код уже использованный другим пользователем"""
    # Генерируем код
    gen_response = await client.post("/api/v2/invites?count=1", headers=admin_headers)
    code = gen_response.json()["codes"][0]

    # Первый пользователь использует код
    use_response1 = await client.post(f"/api/v2/invites/{code}/use", headers=auth_headers)
    assert use_response1.status_code == 200

    # Создаём второго пользователя
    from datetime import UTC, datetime

    from app.auth.auth import hash_password
    from app.models.users import User

    user2 = User(
        id=uuid.uuid4(),
        username="user2",
        email="user2@example.com",
        password_hash=hash_password("password123"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(user2)
    await db_session.commit()

    # Логиним второго пользователя
    token_response = await client.post(
        "/api/v2/user/token",
        data={"username": "user2", "password": "password123"},
    )
    user2_headers = {"Authorization": f"Bearer {token_response.json()['access_token']}"}

    # Второй пользователь пытается использовать тот же код
    use_response2 = await client.post(f"/api/v2/invites/{code}/use", headers=user2_headers)
    assert use_response2.status_code == 404
