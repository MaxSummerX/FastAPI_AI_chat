#!/usr/bin/env python3
"""
Скрипт для генерации invite кодов для регистрации
# Генерация кодов
python scripts/generate_invites.py generate --count 5

# Показать все неиспользованные коды
python scripts/generate_invites.py list
"""

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select


# Добавляем корень проекта в путь
sys.path.append(str(Path(__file__).parent.parent))

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

        print(f"✅ Создано {count} invite кодов:")
        for i, code in enumerate(codes, 1):
            print(f"  {i}. {code}")

        return codes


async def list_unused_codes() -> list[str]:
    """Показывает все неиспользованные коды"""

    async with async_session_maker() as session:
        result = await session.scalars(select(InviteModel.code).where(InviteModel.is_used.is_(False)))

        codes: list[str] = result.all()

        if codes:
            print(f"📋 Неиспользованные коды ({len(codes)}):")
            for i, code in enumerate(codes, 1):
                print(f"  {i}. {code}")
        else:
            print("❌ Нет неиспользованных кодов")

        return codes


async def main() -> None:
    """Главная функция"""
    parser = argparse.ArgumentParser(description="Управление invite кодами")
    parser.add_argument("command", choices=["generate", "list"], help="Команда")
    parser.add_argument("--count", type=int, default=1, help="Количество кодов для генерации")

    args = parser.parse_args()

    if args.command == "generate":
        await generate_invite_codes(args.count)
    elif args.command == "list":
        await list_unused_codes()


if __name__ == "__main__":
    asyncio.run(main())
