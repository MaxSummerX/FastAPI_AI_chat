"""Тесты гонки TOCTOU в регистрации: IntegrityError → 409, а не 500."""

from unittest.mock import AsyncMock

import pytest

from app.application.exceptions.auth import UserAlreadyExistsException
from app.application.services.auth_service import AuthService
from app.domain.exceptions import UniqueConstraintViolationError


@pytest.mark.asyncio
async def test_register_race_username() -> None:
    """Гонка: is_*_unique вернули True, но create упал с IntegrityError → 409."""
    user_repo = AsyncMock()
    user_repo.is_username_unique.return_value = True
    user_repo.is_email_unique.return_value = True
    user_repo.create.side_effect = UniqueConstraintViolationError("Создание пользователя")

    service = AuthService(user_repo, AsyncMock(), AsyncMock(), require_invite=False)

    with pytest.raises(UserAlreadyExistsException):
        await service._register("maks", "maks@example.com", "secret")


@pytest.mark.asyncio
async def test_register_with_invite_race_rolls_back() -> None:
    """Гонка в инвайт-регистрации: flush уронил → rollback + 409."""
    user_repo = AsyncMock()
    user_repo.is_username_unique.return_value = True
    user_repo.is_email_unique.return_value = True
    user_repo.create_without_commit.side_effect = UniqueConstraintViolationError("Создание пользователя")

    invite_repo = AsyncMock()
    invite_repo.get_available_invite.return_value = AsyncMock()
    uow = AsyncMock()

    service = AuthService(user_repo, invite_repo, uow, require_invite=True)

    with pytest.raises(UserAlreadyExistsException):
        await service._register_with_invite("CODE", "max", "max@example.com", "secret")

    uow.rollback.assert_awaited_once()
