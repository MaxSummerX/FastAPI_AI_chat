from loguru import logger
from sqlalchemy import select

from app.database.postgres_db import async_session_maker
from app.models.invites import Invite as InviteModel


async def generate_invite_codes(count: int = 1) -> list[str]:
    """Генерирует указанное количество invite кодов"""

    async with async_session_maker() as session:
        codes = []

        for _ in range(count):
            code = InviteModel.generate_code()
            invite = InviteModel(code=code)
            session.add(invite)
            codes.append(code)

        await session.commit()

        logger.info(f"✅ Создано {count} invite кодов:")

        return codes


async def list_unused_codes() -> list[str]:
    """Показывает все неиспользованные коды"""

    async with async_session_maker() as session:
        result = await session.scalars(select(InviteModel.code).where(InviteModel.is_used.is_(False)))

        codes = result.all()

        if codes:
            logger.info(f"📋 Неиспользованные коды ({len(codes)}):")
        else:
            logger.info("❌ Нет неиспользованных кодов")

        return list(codes)
