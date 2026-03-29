from uuid import UUID

from loguru import logger

from app.application.exceptions.document import DocumentNotFoundError
from app.application.schemas.document import (
    BaseResponse,
    DocumentCreate,
    DocumentResponse,
    DocumentSearchResponse,
    DocumentSearchResult,
    DocumentUpdate,
)
from app.application.schemas.pagination import PaginatedResponse
from app.domain.enums.document import DocumentCategory
from app.domain.repositories.documents import IDocumentRepository


class DocumentService:
    """Сервис для управления документами пользователей."""

    def __init__(self, document_repo: IDocumentRepository) -> None:
        """
        Инициализирует сервис документов.

        Args:
            document_repo: Репозиторий документов для доступа к данным
        """
        self.document_repo = document_repo

    async def get_user_documents(
        self, category: DocumentCategory | None, limit: int, cursor: str | None, user_id: UUID, include_archived: bool
    ) -> PaginatedResponse[BaseResponse]:
        """
        Получить документы пользователя с курсорной пагинацией.

        Args:
            category: Фильтр по категории документа (опционально)
            limit: Максимальное количество документов на странице
            cursor: Курсор из предыдущего ответа для следующей страницы
            user_id: UUID пользователя
            include_archived: Включать ли архивные документы

        Returns:
            PaginatedResponse с документами и метаданными пагинации
        """
        logger.debug(
            f"Запрос на получение документов пользователя {user_id} "
            f"с пагинацией: limit={limit}, cursor={'да' if cursor else 'нет'}"
        )
        documents, next_cursor, has_next = await self.document_repo.get_paginated(
            user_id=user_id,
            cursor=cursor,
            limit=limit,
            category=category,
            include_archived=include_archived,
        )
        logger.debug(
            "Возвращено {} документов, has_next={}, next_cursor={}",
            len(documents),
            has_next,
            "да" if next_cursor else "нет",
        )

        return PaginatedResponse(
            items=[BaseResponse.model_validate(document) for document in documents],
            next_cursor=next_cursor,
            has_next=has_next,
        )

    async def get_user_document(self, document_id: UUID, current_user_id: UUID) -> DocumentResponse:
        """
        Получить документ пользователя по ID.

        Выполняет поиск документа с проверкой прав доступа и статуса архива.
        Возвращает только активные (не архивированные) документы текущего пользователя.

        Args:
            document_id: UUID искомого документа
            current_user_id: Текущий id пользователя

        Returns:
            DocumentResponse: Данные найденного документа

        Raises:
            DocumentNotFoundError: Если документ не найден, принадлежит другому
                пользователю или архивирован
        """
        logger.debug("Запрос на получение документа {} пользователя {}", document_id, current_user_id)
        document = await self.document_repo.get_by_id(document_id=document_id, user_id=current_user_id)

        if not document:
            logger.warning("Документ не найден: document_id={}, user_id={}", document_id, current_user_id)
            raise DocumentNotFoundError(f"Document {document_id} not found")

        return DocumentResponse.model_validate(document)

    async def create_user_document(self, document_data: DocumentCreate, current_user_id: UUID) -> DocumentResponse:
        """
        Создать новый документ для пользователя.

        Создаёт документ с указанными параметрами и сохраняет его в базу данных.
        Категория документа по умолчанию устанавливается в NOTE.

        Args:
            document_data: Данные для создания документа (заголовок, содержимое,
                категория, теги, метаданные)
            current_user_id: Текущий id пользователя

        Returns:
            DocumentResponse: Данные созданного документа с присвоенным UUID
        """
        logger.debug("Запрос на создание документа пользователем {}", current_user_id)
        document = await self.document_repo.create(
            user_id=current_user_id,
            title=document_data.title,
            content=document_data.content,
            metadata_=document_data.metadata_,
            category=document_data.category,
            tags=document_data.tags,
        )

        logger.debug("Документ {} успешно создан", document.id)
        return DocumentResponse.model_validate(document)

    async def update_user_document(
        self, document_id: UUID, document_data: DocumentUpdate, current_user_id: UUID
    ) -> DocumentResponse:
        """
        Обновить данные существующего документа.

        Выполняет частичное обновление документа - обновляются только переданные поля.
        Проверяет право доступа перед изменением. Если данные для обновления не переданы,
        возвращает текущее состояние документа.

        Args:
            document_id: UUID обновляемого документа
            document_data: Данные для обновления (частичные - только изменяемые поля)
            current_user_id: Текущий id пользователя

        Returns:
            DocumentResponse: Обновлённые данные документа

        Raises:
            DocumentNotFoundError: Если документ не найден или принадлежит другому пользователю
        """
        logger.debug("Запрос на обновление документа {} пользователя {}", document_id, current_user_id)
        document = await self.document_repo.get_by_id_for_update(document_id=document_id, user_id=current_user_id)

        if not document:
            logger.warning("Документ не найден: document_id={}, user_id={}", document_id, current_user_id)
            raise DocumentNotFoundError(f"Document {document_id} not found")

        update_data = document_data.model_dump(exclude_unset=True, by_alias=False)

        if not update_data:
            return DocumentResponse.model_validate(document)

        for field, value in update_data.items():
            setattr(document, field, value)

        result = await self.document_repo.save(document)

        logger.debug("Документ пользователя успешно обновлён: {}", document_id)

        return DocumentResponse.model_validate(result)

    async def soft_delete_user_document(self, document_id: UUID, current_user_id: UUID) -> None:
        """
        Удалить документ (мягкое удаление).

        Документ помечается как архивированный (is_archived=True) и исключается
        из основного списка, но остаётся в базе данных. Мягкое удаление позволяет
        восстановить документ при необходимости.

        Args:
            document_id: UUID удаляемого документа
            current_user_id: Текущий id пользователя

        Returns:
            None

        Raises:
            DocumentNotFoundError: Если документ не найден, уже архивирован
                или принадлежит другому пользователю

        Note:
            Функция выполняет мягкое удаление - документ физически остаётся
            в базе данных, но помечается как is_archived=True
        """
        logger.debug("Запрос на удаление документа {} пользователя {}", document_id, current_user_id)
        document = await self.document_repo.get_by_id_for_update(document_id=document_id, user_id=current_user_id)

        if not document:
            logger.warning("Документ не найден: document_id={}, user_id={}", document_id, current_user_id)
            raise DocumentNotFoundError(f"Document {document_id} not found")

        document.is_archived = True

        await self.document_repo.save(document)

        logger.debug("Документ {} помечен как архивированный", document_id)

    async def search_user_documents(
        self,
        query: str,
        limit: int,
        offset: int,
        category: DocumentCategory | None,
        current_user_id: UUID,
    ) -> DocumentSearchResponse:
        """
        Поиск документов пользователя по тексту (PostgreSQL full-text search).

        Выполняет полнотекстовый поиск по содержимому документа.
        Поддерживает русский и английский языки одновременно.
        Результаты сортируются по релевантности (ts_rank).

        Args:
            query: Поисковый запрос
            limit: Максимальное количество результатов
            offset: Смещение для пагинации
            category: Фильтр по категории документа (опционально)
            current_user_id: UUID аутентифицированного пользователя

        Returns:
            DocumentSearchResponse: Результаты поиска с метаданными запроса
        """
        logger.debug("Поиск документов по запросу: '{}' пользователя {}", query, current_user_id)
        result = await self.document_repo.search(
            query=query, limit=limit, offset=offset, category=category, user_id=current_user_id
        )

        documents = [
            DocumentSearchResult(
                relevance_score=score, **DocumentResponse.model_validate(doc, from_attributes=True).model_dump()
            )
            for doc, score in result
        ]

        return DocumentSearchResponse(
            documents=documents,
            query=query,
            limit=limit,
            offset=offset,
        )
