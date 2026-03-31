"""
SQLAlchemy реализация репозитория сообщений.

Конкретная реализация IMessageRepository для персистентности Message сущности
через SQLAlchemy async engine. Следует интерфейсу из domain слоя.
Поддерживает курсорную пагинацию сообщений в беседах.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.message import Message
from app.domain.repositories.messages import IMessageRepository
from app.infrastructure.persistence.pagination import paginate_with_cursor


class MessageSQLAlchemyRepository(IMessageRepository):
    """
    SQLAlchemy реализация репозитория сообщений.

    Предоставляет CRUD операции для Message сущности через SQLAlchemy async.
    Поддерживает курсорную пагинацию для эффективной навигации по истории сообщений.
    """

    def __init__(self, db: AsyncSession):
        """
        Инициализирует репозиторий.

        Args:
            db: Асинхронная сессия SQLAlchemy
        """
        self.db = db

    async def create(
        self,
        conversation_id: UUID,
        role: str,
        content: str,
        model: str,
        metadata_: dict | None = None,
    ) -> Message:
        """
        Создать новое сообщение в беседе.

        Args:
            conversation_id: ID беседы, в которой создаётся сообщение
            role: Роль отправителя (user, assistant, system)
            content: Текст сообщения
            model: Название модели, создавшей сообщение
            metadata_: Дополнительные метаданные сообщения

        Returns:
            Созданный объект Message с присвоенным ID
        """
        message = Message(conversation_id=conversation_id, role=role, content=content, model=model, metadata_=metadata_)
        self.db.add(message)
        await self.db.flush()
        await self.db.commit()
        return message

    async def get_history(self, conversation_id: UUID, limit: int) -> Sequence[Message]:
        """
        Получить историю сообщений беседы.

        Возвращает сообщения в обратном хронологическом порядке
        (от новых к старым) ограниченное количество.

        Args:
            conversation_id: ID беседы
            limit: Максимальное количество сообщений

        Returns:
            Последовательность сообщений от новых к старым
        """
        messages: Sequence[Message] = (
            await self.db.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.timestamp.desc())
                .limit(limit)
            )
        ).all()
        return messages

    async def get_paginated(
        self,
        conversation_id: UUID,
        cursor: str | None,
        limit: int,
    ) -> tuple[Sequence[Message], str | None, bool]:
        """
        Получить сообщения беседы с курсорной пагинацией.

        Использует timestamp поля для курсорной навигации,
        что обеспечивает стабильные результаты при добавлении новых сообщений.

        Args:
            conversation_id: ID беседы
            cursor: Курсор из предыдущего ответа для следующей страницы
            limit: Максимальное количество сообщений на странице

        Returns:
            Кортеж (сообщения, следующий_курсор, есть_ли_следующая_страница)
        """
        query = select(Message).where(Message.conversation_id == conversation_id)

        messages, next_cursor, has_next = await paginate_with_cursor(
            db=self.db,
            query=query,
            cursor=cursor,
            limit=limit,
            model=Message,
            timestamp_field="timestamp",
        )
        return messages, next_cursor, has_next
