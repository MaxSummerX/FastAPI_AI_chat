"""
Репозитории инвайтов.

Интерфейсы для работы с инвайт-кодами в соответствии с принципами clean architecture.
Определяют контракт для управления приглашениями и их использования.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from app.domain.models.invite import Invite


class IInviteRepository(ABC):
    """
    Интерфейс репозитория для работы с инвайтами.

    Определяет контракт для управления инвайт-кодами системы:
    поиск, проверка доступности, пометка как использованный.
    """

    @abstractmethod
    async def get_by_code(self, code: str) -> Invite | None:
        """
        Получить инвайт по коду.

        Args:
            code: Инвайт-код

        Returns:
            Объект Invite или None, если инвайт не найден
        """
        pass

    @abstractmethod
    async def get_available_invite(self, code: str) -> Invite | None:
        """
        Получить доступный (неиспользованный) инвайт по коду.

        Проверяет, что инвайт существует, не использован и не истёк.

        Args:
            code: Инвайт-код

        Returns:
            Объект Invite или None, если инвайт недоступен
        """
        pass

    @abstractmethod
    async def get_available_invites(self) -> Sequence[Invite]:
        """
        Получить все доступные (неиспользованные) инвайты.

        Returns:
            Последовательность всех доступных объектов Invite
        """
        pass

    @abstractmethod
    async def mark_as_used(self, invite: Invite, user_id: UUID) -> Invite:
        """
        Пометить инвайт как использованный.

        Args:
            invite: Объект инвайта
            user_id: ID пользователя, использовавшего инвайт

        Returns:
            Обновлённый объект Invite
        """
        pass

    @abstractmethod
    async def save(self, invite: Invite) -> Invite:
        """
        Сохранить изменения инвайта.

        Args:
            invite: Объект Invite с обновлёнными данными

        Returns:
            Сохранённый объект Invite
        """
        pass

    @abstractmethod
    async def delete_if_not_used(self, invite: Invite) -> bool:
        """
        Удалить инвайт, только если он не был использован.

        Безопасное удаление - предотвращает удаление уже использованных инвайтов.

        Args:
            invite: Объект Invite для удаления

        Returns:
            True если инвайт удалён, False если уже был использован
        """
        pass

    @abstractmethod
    async def bulk_create(self, invites: list[Invite]) -> None:
        """
        Массово создать инвайты (одна транзакция).

        Args:
            invites: Список объектов Invite для создания
        """
        pass

    @abstractmethod
    async def delete_all_unused(self) -> int:
        """
        Удалить все неиспользованные инвайты.

        Удаляет все инвайты с is_used=False. Полезно для очистки старых кодов.

        Returns:
            Количество удалённых инвайтов
        """
        pass
