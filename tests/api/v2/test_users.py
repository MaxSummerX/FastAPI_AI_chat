"""
Тесты для user endpoints API v2.

Покрывает все основные сценарии:
- Регистрация
- Авторизация
- Обновление профиля
- Изменение email, пароля, username
- Обработка ошибок
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.users import User as UserModel


# ============================================================
# GET /user - базовая информация о пользователе
# ============================================================


@pytest.mark.asyncio
async def test_get_base_user_unauthorized(client: AsyncClient) -> None:
    """Тест: неавторизованный запрос к /user"""
    response = await client.get("/api/v2/user")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_base_user_success(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: успешное получение базовой информации"""
    response = await client.get("/api/v2/user", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert "id" in data
    assert "username" in data
    assert "email" in data
    assert "is_active" in data
    assert "is_verified" in data
    # Поля профиля не должны быть в базовом ответе
    assert "first_name" not in data
    assert "last_name" not in data


# ============================================================
# GET /user/info - полная информация о пользователе
# ============================================================


@pytest.mark.asyncio
async def test_get_full_user_info_success(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: успешное получение полной информации"""
    response = await client.get("/api/v2/user/info", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert "id" in data
    assert "username" in data
    assert "email" in data
    assert "first_name" in data
    assert "last_name" in data
    assert "created_at" in data
    assert "updated_at" in data


# ============================================================
# POST /user/register - регистрация нового пользователя
# ============================================================


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient) -> None:
    """Тест: успешная регистрация"""
    response = await client.post(
        "/api/v2/user/register",
        json={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "NewPassword123!",
        },
    )
    assert response.status_code == 201

    data = response.json()
    assert "id" in data
    assert data["username"] == "newuser"
    assert data["email"] == "newuser@example.com"
    assert "password" not in data  # Пароль не должен возвращаться
    assert "password_hash" not in data


@pytest.mark.asyncio
async def test_register_duplicate_username(client: AsyncClient, test_user: UserModel) -> None:
    """Тест: регистрация с существующим username"""
    response = await client.post(
        "/api/v2/user/register",
        json={
            "username": "testuser",  # Уже занят
            "email": "another@example.com",
            "password": "NewPassword123!",
        },
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, test_user: UserModel) -> None:
    """Тест: регистрация с существующим email"""
    response = await client.post(
        "/api/v2/user/register",
        json={
            "username": "another",
            "email": "test@example.com",  # Уже занят
            "password": "NewPassword123!",
        },
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient) -> None:
    """Тест: регистрация со слабым паролем"""
    response = await client.post(
        "/api/v2/user/register",
        json={
            "username": "weakuser",
            "email": "weak@example.com",
            "password": "weak",  # Не соответствует требованиям
        },
    )
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_register_short_username(client: AsyncClient) -> None:
    """Тест: регистрация с коротким username"""
    response = await client.post(
        "/api/v2/user/register",
        json={
            "username": "ab",  # М меньше 3 символов
            "email": "test@example.com",
            "password": "ValidPassword123!",
        },
    )
    assert response.status_code == 422


# ============================================================
# POST /user/token - авторизация (логин)
# ============================================================


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user: UserModel) -> None:
    """Тест: успешный вход"""
    response = await client.post(
        "/api/v2/user/token",
        data={
            "username": "testuser",
            "password": "TestPassword123!",
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert "expires_in" in data


@pytest.mark.asyncio
async def test_login_with_email(client: AsyncClient, test_user: UserModel) -> None:
    """Тест: вход с email вместо username"""
    response = await client.post(
        "/api/v2/user/token",
        data={
            "username": "test@example.com",  # Email вместо username
            "password": "TestPassword123!",
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, test_user: UserModel) -> None:
    """Тест: вход с неверным паролем"""
    response = await client.post(
        "/api/v2/user/token",
        data={
            "username": "testuser",
            "password": "WrongPassword123!",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient) -> None:
    """Тест: вход несуществующего пользователя"""
    response = await client.post(
        "/api/v2/user/token",
        data={
            "username": "nonexistent",
            "password": "SomePassword123!",
        },
    )
    assert response.status_code == 401


# ============================================================
# POST /user/refresh-token - обновление access токена
# ============================================================


@pytest.mark.asyncio
async def test_refresh_token_success(client: AsyncClient, test_user: UserModel) -> None:
    """Тест: успешное обновление токена"""
    # Сначала логинимся
    login_response = await client.post(
        "/api/v2/user/token",
        data={
            "username": "testuser",
            "password": "TestPassword123!",
        },
    )
    tokens = login_response.json()
    refresh_token = tokens["refresh_token"]

    # Обновляем токен
    response = await client.post(
        "/api/v2/user/refresh-token",
        params={"refresh_token": refresh_token},
    )
    assert response.status_code == 200

    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_refresh_token_invalid(client: AsyncClient) -> None:
    """Тест: обновление с невалидным токеном"""
    response = await client.post(
        "/api/v2/user/refresh-token",
        params={"refresh_token": "invalid_token"},
    )
    assert response.status_code == 401


# ============================================================
# PATCH /user/update - обновление профиля
# ============================================================


@pytest.mark.asyncio
async def test_update_profile_success(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: успешное обновление профиля"""
    response = await client.patch(
        "/api/v2/user/update",
        headers=auth_headers,
        json={
            "first_name": "Test",
            "last_name": "User",
            "bio": "Test bio",
            "timezone": "Europe/Moscow",
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["first_name"] == "Test"
    assert data["last_name"] == "User"
    assert data["bio"] == "Test bio"
    assert data["timezone"] == "Europe/Moscow"


@pytest.mark.asyncio
async def test_update_profile_empty(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: обновление с пустыми данными"""
    response = await client.patch(
        "/api/v2/user/update",
        headers=auth_headers,
        json={},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_update_profile_unauthorized(client: AsyncClient) -> None:
    """Тест: обновление без авторизации"""
    response = await client.patch(
        "/api/v2/user/update",
        json={
            "first_name": "Test",
        },
    )
    assert response.status_code == 401


# ============================================================
# POST /user/update-email - обновление email
# ============================================================


@pytest.mark.asyncio
async def test_update_email_success(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: успешное обновление email"""
    response = await client.post(
        "/api/v2/user/update-email",
        headers=auth_headers,
        json={
            "current_password": "TestPassword123!",
            "new_email": "newemail@example.com",
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["email"] == "newemail@example.com"


@pytest.mark.asyncio
async def test_update_email_wrong_password(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: обновление email с неверным паролем"""
    response = await client.post(
        "/api/v2/user/update-email",
        headers=auth_headers,
        json={
            "current_password": "WrongPassword123!",
            "new_email": "newemail@example.com",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_email_same_as_current(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: обновление email на текущий"""
    response = await client.post(
        "/api/v2/user/update-email",
        headers=auth_headers,
        json={
            "current_password": "TestPassword123!",
            "new_email": "test@example.com",  # Текущий email
        },
    )
    assert response.status_code == 200


# ============================================================
# POST /user/update-password - обновление пароля
# ============================================================


@pytest.mark.asyncio
async def test_update_password_success(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: успешное обновление пароля"""
    response = await client.post(
        "/api/v2/user/update-password",
        headers=auth_headers,
        json={
            "current_password": "TestPassword123!",
            "password": "NewPassword123!",
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_update_password_wrong_current(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: обновление пароля с неверным текущим паролем"""
    response = await client.post(
        "/api/v2/user/update-password",
        headers=auth_headers,
        json={
            "current_password": "WrongPassword123!",
            "password": "NewPassword123!",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_password_weak_new(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: обновление на слабый пароль"""
    response = await client.post(
        "/api/v2/user/update-password",
        headers=auth_headers,
        json={
            "current_password": "TestPassword123!",
            "password": "weak",  # Слабый пароль
        },
    )
    assert response.status_code == 422


# ============================================================
# POST /user/update-username - обновление username
# ============================================================


@pytest.mark.asyncio
async def test_update_username_success(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: успешное обновление username"""
    response = await client.post(
        "/api/v2/user/update-username",
        headers=auth_headers,
        json={
            "current_password": "TestPassword123!",
            "username": "newusername",
        },
    )
    assert response.status_code == 200

    data = response.json()
    assert data["username"] == "newusername"


@pytest.mark.asyncio
async def test_update_username_wrong_password(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: обновление username с неверным паролем"""
    response = await client.post(
        "/api/v2/user/update-username",
        headers=auth_headers,
        json={
            "current_password": "WrongPassword123!",
            "username": "newusername",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_username_short(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: обновление username на короткий"""
    response = await client.post(
        "/api/v2/user/update-username",
        headers=auth_headers,
        json={
            "current_password": "TestPassword123!",
            "username": "ab",  # Слишком короткий
        },
    )
    assert response.status_code == 422


# ============================================================
# Регистрация с инвайтом
# ============================================================


@pytest.mark.asyncio
async def test_register_with_invite_success(client: AsyncClient, db_session: AsyncSession) -> None:
    """Тест: успешная регистрация с инвайтом"""
    import uuid
    from datetime import UTC, datetime

    from app.models.invites import Invite as InviteModel

    # Создаём инвайт
    invite = InviteModel(
        id=uuid.uuid4(),
        code="TESTCODE123",
        is_used=False,
        created_at=datetime.now(UTC),
    )
    db_session.add(invite)
    await db_session.commit()

    # Регистрируемся с инвайтом
    response = await client.post(
        "/api/v2/user/register_with_invite?invite_code=TESTCODE123",
        json={
            "username": "inviteduser",
            "email": "invited@example.com",
            "password": "InvitedPassword123!",
        },
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_register_with_invalid_invite(client: AsyncClient) -> None:
    """Тест: регистрация с неверным инвайтом"""
    response = await client.post(
        "/api/v2/user/register_with_invite?invite_code=INVALID",
        json={
            "username": "inviteduser",
            "email": "invited@example.com",
            "password": "InvitedPassword123!",
        },
    )
    assert response.status_code == 403
