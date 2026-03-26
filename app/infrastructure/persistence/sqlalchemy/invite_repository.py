"""
SQLAlchemy реализация репозитория инвайтов.

Конкретная реализация IInviteRepository для персистентности Invite сущности
через SQLAlchemy async engine. Следует интерфейсу из domain слоя.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.invite import Invite
from app.domain.repositories.invites import IInviteRepository


class InviteSQLAlchemyRepository(IInviteRepository):
    """
    SQLAlchemy реализация репозитория для инвайтов.

    Предоставляет CRUD операции для Invite сущности через SQLAlchemy async.
    Отслеживает использование инвайтов и предотвращает повторное использование.
    """

    def __init__(self, db: AsyncSession):
        """
        Инициализирует репозиторий.

        Args:
            db: Асинхронная сессия SQLAlchemy
        """
        self.db = db

    async def get_by_code(self, code: str) -> Invite | None:
        """
        Получить инвайт по коду.

        Args:
            code: Инвайт-код

        Returns:
            Объект Invite или None если не найден
        """
        result: Invite | None = await self.db.scalar(select(Invite).where(Invite.code == code))
        return result

    async def get_available_invite(self, code: str) -> Invite | None:
        """
        Получить доступный (неиспользованный) инвайт по коду.

        Args:
            code: Инвайт-код

        Returns:
            Объект Invite или None если не найден или уже использован
        """
        result: Invite | None = await self.db.scalar(
            select(Invite).where(Invite.code == code, Invite.is_used.is_(False))
        )
        return result

    async def get_available_invites(self, skip: int, limit: int) -> Sequence[Invite]:
        """
        Получить список доступных (неиспользованных) инвайтов с пагинацией.

        Args:
            skip: Количество записей для пропуска (offset)
            limit: Максимальное количество записей для возврата

        Returns:
            Последовательность доступных объектов Invite
        """
        result = await self.db.scalars(select(Invite).where(Invite.is_used.is_(False)).offset(skip).limit(limit))
        invites: Sequence[Invite] = result.all()
        return invites

    async def mark_as_used(self, invite: Invite, user_id: UUID) -> Invite:
        """
        Пометить инвайт как использованный.

        Устанавливает флаг is_used, сохраняет ID пользователя и время использования.

        Args:
            invite: Объект инвайта
            user_id: ID пользователя, использовавшего инвайт

        Returns:
            Обновлённый объект Invite
        """
        invite.is_used = True
        invite.used_by_user_id = user_id
        invite.used_at = datetime.now(UTC)
        return await self.save(invite)

    async def save(self, invite: Invite) -> Invite:
        """
        Сохранить изменения инвайта.

        Args:
            invite: Объект Invite с обновлёнными данными

        Returns:
            Сохранённый объект Invite
        """
        await self.db.commit()
        await self.db.refresh(invite)
        return invite

    async def delete_if_not_used(self, invite: Invite) -> bool:
        """
        Удалить инвайт, только если он не был использован.

        Безопасное удаление - предотвращает удаление уже использованных инвайтов.

        Args:
            invite: Объект Invite для удаления

        Returns:
            True если инвайт удалён, False если уже был использован
        """
        if invite.is_used:
            return False

        await self.db.delete(invite)
        await self.db.commit()
        return True

    async def bulk_create(self, invites: Sequence[Invite]) -> Sequence[Invite]:
        """
        Массово создать инвайты (одна транзакция).

        При наличии дубликатов кодов пропускает их и возвращает только успешно созданные.

        Args:
            invites: Последовательность объектов Invite для создания

        Returns:
            Список успешно созданных инвайтов с id и created_at из БД
        """
        for invite in invites:
            self.db.add(invite)

        await self.db.commit()

        created_invites = []
        for invite in invites:
            try:
                await self.db.refresh(invite)
                created_invites.append(invite)
            except IntegrityError:
                # Пропускаем дубликаты кодов
                continue

        return created_invites

    async def delete_all_unused(self) -> int:
        """
        Удалить все неиспользованные инвайты.

        Удаляет все инвайты с is_used=False. Полезно для очистки старых кодов.

        Returns:
            Количество удалённых инвайтов
        """
        result = await self.db.execute(select(Invite).where(Invite.is_used.is_(False)))
        invites = result.scalars().all()

        count = len(invites)
        for invite in invites:
            await self.db.delete(invite)

        await self.db.commit()
        return count
