from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_admin_user, get_current_user
from app.depends.db_depends import get_async_postgres_db
from app.models.invites import Invite as InviteModel
from app.models.users import User as UserModel
from app.schemas.invites import InviteCodeResponse, InviteCreateResponse, InviteListResponse


router = APIRouter(prefix="/invites", tags=["Invites_V2"])


@router.post("", status_code=status.HTTP_201_CREATED, summary="Сгенерировать инвайт-коды")
async def generate_invite_codes(
    count: int = Query(1, ge=1, le=100, description="Количество кодов для генерации (1-100)"),
    current_admin: UserModel = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> InviteCreateResponse:
    """
    Генерирует указанное количество уникальных инвайт-кодов.

    Требуются права администратора. Коды можно использовать для регистрации новых пользователей.
    """
    logger.info(f"Запрос на генерацию {count} инвайт-кодов от администратора {current_admin.id}")

    codes = []

    for _ in range(count):
        code = InviteModel.generate_code()
        invite = InviteModel(code=code)
        db.add(invite)
        codes.append(code)

    await db.commit()

    logger.info(f"Успешно сгенерировано {count} инвайт-кодов администратором {current_admin.id}")

    return InviteCreateResponse(codes=codes, count=len(codes))


@router.get("/unused", status_code=status.HTTP_200_OK, summary="Получить неиспользованные инвайт-коды")
async def list_unused_codes(
    current_admin: UserModel = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> InviteListResponse:
    """
    Возвращает список всех неиспользованных инвайт-кодов.

    Требуются права администратора.
    """
    logger.info(f"Запрос на получение неиспользованных инвайт-кодов от администратора {current_admin.id}")

    result = await db.scalars(select(InviteModel).where(InviteModel.is_used.is_(False)))
    invites = result.all()

    codes = [
        InviteCodeResponse(id=invite.id, code=invite.code, is_used=invite.is_used, created_at=invite.created_at)
        for invite in invites
    ]

    logger.info(f"Найдено {len(codes)} неиспользованных инвайт-кодов")

    return InviteListResponse(codes=codes, count=len(codes))


@router.get("/{code}", status_code=status.HTTP_200_OK, summary="Проверить инвайт-код")
async def check_invite_code(
    code: str,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> InviteCodeResponse:
    """
    Проверяет статус инвайт-кода.

    Возвращает информацию о коде: используется ли он и когда был создан.
    """
    logger.info(f"Запрос на проверку инвайт-кода от пользователя {current_user.id}")

    result = await db.scalars(select(InviteModel).where(InviteModel.code == code))

    invite = result.first()

    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite code not found")

    return InviteCodeResponse(id=invite.id, code=invite.code, is_used=invite.is_used, created_at=invite.created_at)


@router.post("/{code}/use", status_code=status.HTTP_200_OK, summary="Использовать инвайт-код")
async def use_invite_code(
    code: str,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> dict[str, str]:
    """
    Помечает инвайт-код как использованный текущим пользователем.

    Обычно вызывается автоматически при регистрации с инвайт-кодом.
    """
    logger.info(f"Запрос на использование инвайт-кода от пользователя {current_user.id}")

    result = await db.scalars(select(InviteModel).where(InviteModel.code == code, InviteModel.is_used.is_(False)))

    invite = result.first()

    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite code not found or already used")

    # Помечаем как использованный
    from datetime import UTC, datetime

    invite.is_used = True
    invite.used_by_user_id = current_user.id
    invite.used_at = datetime.now(UTC)

    await db.commit()

    logger.info(f"Инвайт-код {code[:8]}... использован пользователем {current_user.id}")

    return {"message": "Invite code used successfully", "code": code}


@router.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить инвайт-код")
async def delete_invite_code(
    code: str,
    current_admin: UserModel = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> None:
    """
    Удаляет инвайт-код из системы.

    Требуются права администратора.
    """
    logger.info(f"Запрос на удаление инвайт-кода от администратора {current_admin.id}")

    result = await db.scalars(select(InviteModel).where(InviteModel.code == code))
    invite = result.first()

    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite code not found")

    await db.delete(invite)
    await db.commit()

    logger.info(f"Инвайт-код {code[:8]}... удалён администратором {current_admin.id}")
