"""
SQLAlchemy реализация репозитория бесед.

Конкретная реализация IConversationRepository для персистентности Conversation сущности
через SQLAlchemy async engine. Следует интерфейсу из domain слоя.
Поддерживает курсорную пагинацию и работу с импортированными беседами.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.conversation import Conversation
from app.domain.repositories.conversations import IConversationRepository
from app.infrastructure.persistence.pagination import paginate_with_cursor


class ConversationSQLAlchemyRepository(IConversationRepository):
    """
    SQLAlchemy реализация репозитория бесед.

    Предоставляет CRUD операции для Conversation сущности через SQLAlchemy async.
    Все запросы фильтруют архивированные беседы (is_archived=True) по умолчанию.
    Поддерживает импорт диалогов из внешних источников.
    """

    def __init__(self, db: AsyncSession):
        """
        Инициализирует репозиторий.

        Args:
            db: Асинхронная сессия SQLAlchemy
        """
        self.db = db

    @staticmethod
    def _base_query(conversation_id: UUID, user_id: UUID) -> Select[tuple[Conversation]]:
        """
        Базовый запрос для получения беседы пользователя.

        Фильтрует по ID, владельцу и исключает архивированные беседы.

        Args:
            conversation_id: Уникальный идентификатор беседы
            user_id: ID пользователя, владельца беседы

        Returns:
            SQLAlchemy Select объект для выполнения запроса
        """
        return select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
            Conversation.is_archived.is_(False),
        )

    async def get_paginated(
        self,
        user_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> tuple[Sequence[Conversation], str | None, bool]:
        """
        Получить беседы пользователя с курсорной пагинацией.

        Использует индексы (created_at, id) для эффективной пагинации.

        Args:
            user_id: ID пользователя, владельца бесед
            cursor: Курсор из предыдущего ответа для следующей страницы
            limit: Максимальное количество бесед на странице

        Returns:
            Кортеж (беседы, следующий_курсор, есть_ли_следующая_страница)
        """
        query = select(Conversation).where(Conversation.user_id == user_id)

        conversations, next_cursor, has_next = await paginate_with_cursor(
            db=self.db,
            query=query,
            cursor=cursor,
            limit=limit,
            model=Conversation,
        )

        return conversations, next_cursor, has_next

    async def get_by_id(
        self,
        conversation_id: UUID,
        user_id: UUID,
    ) -> Conversation | None:
        """
        Получить беседу по ID.

        Args:
            conversation_id: Уникальный идентификатор беседы
            user_id: ID пользователя, владельца беседы

        Returns:
            Объект Conversation или None если не найден или архивирован
        """
        result: Conversation | None = await self.db.scalar(self._base_query(conversation_id, user_id))
        return result

    async def create(
        self,
        user_id: UUID,
        title: str | None,
    ) -> Conversation:
        """
        Создать новую беседу.

        Args:
            user_id: ID пользователя, владельца беседы
            title: Название беседы (опционально)

        Returns:
            Созданный объект Conversation с id и created_at из БД
        """
        conversation = Conversation(
            user_id=user_id,
            title=title or "New conversation",
        )

        self.db.add(conversation)
        await self.db.commit()
        await self.db.refresh(conversation)

        return conversation

    async def create_from_import(
        self,
        user_id: UUID,
        title: str | None,
        source: str | None = None,
        source_id: UUID | None = None,
        is_imported: bool = True,
    ) -> Conversation:
        """
        Создать беседу из импортированных данных.

        Используется при импорте диалогов из внешних источников
        (Claude.ai, ChatGPT и др.) для сохранения метаданных источника.

        Args:
            user_id: ID пользователя, владельца беседы
            title: Название беседы
            source: Источник импорта (например, "claude", "gpt")
            source_id: ID беседы в источнике импорта
            is_imported: Флаг, помечающий беседу как импортированную

        Returns:
            Созданный объект Conversation с id и created_at из БД
        """
        conversation = Conversation(
            user_id=user_id,
            title=title,
            source=source,
            source_id=source_id,
            is_imported=is_imported,
        )

        self.db.add(conversation)
        await self.db.commit()
        await self.db.refresh(conversation)

        return conversation

    async def delete(self, conversation: Conversation) -> None:
        """
        Удалить беседу.

        Args:
            conversation: Объект Conversation для удаления
        """
        await self.db.delete(conversation)
        await self.db.commit()

    async def save(self, conversation: Conversation) -> Conversation:
        """
        Сохранить изменения беседы.

        Args:
            conversation: Объект Conversation с обновлёнными данными

        Returns:
            Сохранённый объект Conversation
        """
        await self.db.commit()
        await self.db.refresh(conversation)
        return conversation

    async def get_by_id_for_update(self, conversation_id: UUID, user_id: UUID) -> Conversation | None:
        """
        Получить беседу по ID с блокировкой для обновления.

        Использует SELECT ... FOR UPDATE для предотвращения race conditions.
        Применяется когда нужно обновить данные с гарантией, что они не изменились.

        Args:
            conversation_id: Уникальный идентификатор беседы
            user_id: ID пользователя, владельца беседы

        Returns:
            Объект Conversation или None если не найден или архивирован
        """
        result: Conversation | None = await self.db.scalar(self._base_query(conversation_id, user_id).with_for_update())
        return result
