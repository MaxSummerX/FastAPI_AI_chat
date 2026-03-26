from uuid import UUID

from loguru import logger

from app.application.schemas.invite import (
    InviteCodeResponse,
    InviteDeleteResponse,
    InviteListResponse,
)
from app.domain.models.invite import Invite
from app.domain.repositories.invites import IInviteRepository


class InviteService:
    """Сервис для управления инвайт-кодами."""

    def __init__(self, invite_repo: IInviteRepository):
        self.invite_repo = invite_repo

    async def generate_invite_codes(self, count: int, admin_id: UUID) -> InviteListResponse:
        """
        Сгенерировать указанное количество инвайт-кодов.

        Использует bulk_create для массового создания в одной транзакции.
        Возвращает полные созданные объекты с id и created_at из БД.

        Args:
            count: Количество кодов для генерации
            admin_id: ID администратора, который инициировал генерацию

        Returns:
            Список созданных инвайт-кодов с полной информацией
        """
        logger.info("Запрос на генерацию {} инвайт-кодов от администратора {}", count, admin_id)

        invites = []

        for _ in range(count):
            code = Invite.generate_code()
            invite = Invite(code=code)
            invites.append(invite)

        created_invites = await self.invite_repo.bulk_create(invites)

        codes = [InviteCodeResponse.model_validate(invite) for invite in created_invites]

        logger.info("Успешно сгенерировано {} инвайт-кодов администратором {}", count, admin_id)

        return InviteListResponse(codes=codes, count=len(codes))

    async def unused_codes(self, skip: int, limit: int, admin_id: UUID) -> InviteListResponse:
        """
        Получить список неиспользованных инвайтов с пагинацией.

        Args:
            skip: Количество записей для пропуска (offset)
            limit: Максимальное количество записей для возврата
            admin_id: ID администратора, запрашивающего данные

        Returns:
            Список неиспользованных инвайт-кодов с пагинацией
        """
        logger.info("Запрос на получение инвайт-кодов от администратора {}", admin_id)
        invites = await self.invite_repo.get_available_invites(skip, limit)

        codes = [
            InviteCodeResponse(id=invite.id, code=invite.code, is_used=invite.is_used, created_at=invite.created_at)
            for invite in invites
        ]

        return InviteListResponse(codes=codes, count=len(codes))

    async def delete_all_unused(self, admin_id: UUID) -> InviteDeleteResponse:
        """
        Удалить все неиспользованные инвайты.

        Удаляет все инвайты с is_used=False.
        Полезно для очистки старых кодов.

        Args:
            admin_id: ID администратора, который инициировал удаление

        Returns:
            Количество удалённых инвайтов
        """
        count = await self.invite_repo.delete_all_unused()
        logger.info("Удалёно {} неиспользованных инвайтов, администратором {}", count, admin_id)

        return InviteDeleteResponse(deleted_count=count)
