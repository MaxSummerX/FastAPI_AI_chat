from uuid import UUID

from loguru import logger

from app.application.exceptions.conversation import ConversationNotFoundError
from app.application.schemas.conversation import ConversationCreate, ConversationResponse, ConversationUpdate
from app.application.schemas.pagination import PaginatedResponse
from app.domain.repositories.conversations import IConversationRepository


class ConversationService:
    """Сервис для управления беседами пользователей."""

    def __init__(self, conversation_repo: IConversationRepository) -> None:
        """
        Инициализирует сервис бесед.

        Args:
            conversation_repo: Репозиторий бесед для доступа к данным
        """
        self.conversation_repo = conversation_repo

    async def get_user_conversations(
        self, limit: int, cursor: str | None, user_id: UUID
    ) -> PaginatedResponse[ConversationResponse]:
        """
        Получить беседы пользователя с курсорной пагинацией.

        Args:
            limit: Максимальное количество бесед на странице
            cursor: Курсор из предыдущего ответа для следующей страницы
            user_id: UUID пользователя

        Returns:
            PaginatedResponse с беседами и метаданными пагинации
        """
        logger.debug(
            "Запрос на получение бесед пользователя {} с пагинацией: limit={}, cursor={}",
            user_id,
            limit,
            "да" if cursor else "нет",
        )
        conversations, next_cursor, has_next = await self.conversation_repo.get_paginated(
            user_id=user_id, cursor=cursor, limit=limit
        )
        logger.debug(
            "Возвращено {} бесед, has_next={}, next_cursor={}",
            len(conversations),
            has_next,
            "да" if next_cursor else "нет",
        )

        return PaginatedResponse(
            items=[ConversationResponse.model_validate(conversation) for conversation in conversations],
            next_cursor=next_cursor,
            has_next=has_next,
        )

    async def create_conversation(self, conversation_data: ConversationCreate, user_id: UUID) -> ConversationResponse:
        """
        Создать новую беседу для пользователя.

        Args:
            conversation_data: Данные для создания беседы (заголовок)
            user_id: UUID пользователя

        Returns:
            ConversationResponse: Данные созданной беседы с присвоенным UUID
        """
        logger.debug("Запрос на создание беседы пользователем {}", user_id)

        conversation = await self.conversation_repo.create(
            user_id=user_id, title=conversation_data.title or "New conversation"
        )

        logger.debug("Создана беседа {} для пользователя {}", conversation.id, user_id)

        return ConversationResponse.model_validate(conversation)

    async def update_conversation(
        self, conversation_id: UUID, conversation_data: ConversationUpdate, user_id: UUID
    ) -> ConversationResponse:
        """
        Обновить данные существующей беседы.

        Выполняет частичное обновление беседы - обновляются только переданные поля.
        Проверяет право доступа перед изменением. Если данные для обновления не переданы,
        возвращает текущее состояние беседы.

        Args:
            conversation_id: UUID обновляемой беседы
            conversation_data: Данные для обновления (частичные - только изменяемые поля)
            user_id: UUID пользователя

        Returns:
            ConversationResponse: Обновлённые данные беседы

        Raises:
            ConversationNotFoundError: Если беседа не найдена или принадлежит другому пользователю
        """
        logger.debug("Запрос на обновление беседы {} пользователя {}", conversation_id, user_id)

        conversation = await self.conversation_repo.get_by_id_for_update(
            conversation_id=conversation_id, user_id=user_id
        )
        if not conversation:
            logger.warning("Беседа не найдена: conversation_id={}, user_id={}", conversation_id, user_id)
            raise ConversationNotFoundError(f"Conversation {conversation_id} not found")

        update_data = conversation_data.model_dump(exclude_unset=True, by_alias=False)

        if not update_data:
            return ConversationResponse.model_validate(conversation)

        for field, value in update_data.items():
            setattr(conversation, field, value)

        result = await self.conversation_repo.save(conversation)

        logger.debug("Обновлена беседа {} для пользователя {}", conversation_id, user_id)

        return ConversationResponse.model_validate(result)

    async def delete_conversation(self, conversation_id: UUID, user_id: UUID) -> None:
        """
        Удалить беседу.

        Выполняет полное удаление беседы из базы данных.
        Использует блокировку для предотвращения race conditions.

        Args:
            conversation_id: UUID удаляемой беседы
            user_id: UUID пользователя

        Raises:
            ConversationNotFoundError: Если беседа не найдена или принадлежит другому пользователю
        """
        logger.debug("Запрос на удаление беседы {} пользователем {}", conversation_id, user_id)

        conversation = await self.conversation_repo.get_by_id_for_update(
            conversation_id=conversation_id, user_id=user_id
        )

        if not conversation:
            logger.warning("Беседа не найдена: conversation_id={}, user_id={}", conversation_id, user_id)
            raise ConversationNotFoundError(f"Conversation {conversation_id} not found")

        await self.conversation_repo.delete(conversation=conversation)

        logger.debug("Удалена беседа {}", conversation_id)
