"""
SQLAlchemy реализация репозитория документов.

Конкретная реализация IDocumentRepository для персистентности Document сущности
через SQLAlchemy async engine. Следует интерфейсу из domain слоя.
Поддерживает курсорную пагинацию и полнотекстовый поиск через TSVECTOR.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums.document import DocumentCategory
from app.domain.models.document import Document
from app.domain.repositories.documents import IDocumentRepository
from app.infrastructure.persistence.pagination import paginate_with_cursor


class DocumentSQLAlchemyRepository(IDocumentRepository):
    """
    SQLAlchemy реализация репозитория документов.

    Предоставляет CRUD операции для Document сущности через SQLAlchemy async.
    Все запросы фильтруют архивные документы (is_archived=True) по умолчанию.
    Поддерживает полнотекстовый поиск через PostgreSQL TSVECTOR.
    """

    def __init__(self, db: AsyncSession):
        """
        Инициализирует репозиторий.

        Args:
            db: Асинхронная сессия SQLAlchemy
        """
        self.db = db

    @staticmethod
    def _base_query(document_id: UUID, user_id: UUID) -> Select[tuple[Document]]:
        """
        Базовый запрос для получения документа пользователя.

        Фильтрует по ID, владельцу и исключает архивные документы.

        Args:
            document_id: Уникальный идентификатор документа
            user_id: ID пользователя, владельца документа

        Returns:
            SQLAlchemy Select объект для выполнения запроса
        """
        return select(Document).where(
            Document.id == document_id,
            Document.user_id == user_id,
            Document.is_archived.is_(False),
        )

    async def get_paginated(
        self,
        user_id: UUID,
        cursor: str | None,
        limit: int,
        category: DocumentCategory | None = None,
        include_archived: bool = False,
    ) -> tuple[Sequence[Document], str | None, bool]:
        """
        Получить документы пользователя с курсорной пагинацией.

        Использует индексы (created_at, id) для эффективной пагинации.

        Args:
            user_id: ID пользователя, владельца документов
            cursor: Курсор из предыдущего ответа для следующей страницы
            limit: Максимальное количество документов на странице
            category: Фильтр по категории документа (опционально)
            include_archived: Включать ли архивные документы в результаты

        Returns:
            Кортеж (документы, следующий_курсор, есть_ли_следующая_страница)
        """
        conditions = [Document.user_id == user_id]

        if category:
            conditions.append(Document.category == category)

        if not include_archived:
            conditions.append(Document.is_archived.is_(False))

        query = select(Document).where(*conditions)

        documents, next_cursor, has_next = await paginate_with_cursor(
            db=self.db,
            query=query,
            cursor=cursor,
            limit=limit,
            model=Document,
        )

        return documents, next_cursor, has_next

    async def get_by_id(self, document_id: UUID, user_id: UUID) -> Document | None:
        """
        Получить документ по ID.

        Args:
            document_id: Уникальный идентификатор документа
            user_id: ID пользователя, владельца документа

        Returns:
            Объект Document или None если не найден или архивный
        """
        result: Document | None = await self.db.scalar(self._base_query(document_id, user_id))
        return result

    async def create(
        self,
        user_id: UUID,
        title: str | None,
        content: str,
        category: DocumentCategory | None,
        metadata_: dict | None,
        tags: list | None,
    ) -> Document:
        """
        Создать новый документ.

        TSVECTOR поле search_vector заполняется автоматически триггером БД.

        Args:
            user_id: ID пользователя, владельца документа
            title: Заголовок документа
            content: Содержимое документа
            category: Категория документа из DocumentCategory (опционально)
            metadata_: Дополнительные метаданные в формате JSON (опционально)
            tags: Список тегов для организации документов (опционально)

        Returns:
            Созданный объект Document с id и created_at из БД
        """
        document = Document(
            user_id=user_id,
            title=title,
            content=content,
            category=category,
            metadata_=metadata_,
            tags=tags,
        )

        self.db.add(document)
        await self.db.commit()
        await self.db.refresh(document)

        return document

    async def save(self, document: Document) -> Document:
        """
        Сохранить изменения документа.

        Args:
            document: Объект Document с обновлёнными данными

        Returns:
            Сохранённый объект Document
        """
        await self.db.commit()
        await self.db.refresh(document)
        return document

    async def search(
        self,
        query: str,
        limit: int,
        offset: int,
        category: DocumentCategory | None,
        user_id: UUID,
    ) -> Sequence[tuple[Document, float]]:
        """
        Полнотекстовый поиск по документам пользователя.

        Использует PostgreSQL TSVECTOR для поиска на русском и английском.
        Результаты сортируются по релевантности (ts_rank).

        Args:
            query: Поисковый запрос (текст для поиска)
            limit: Максимальное количество результатов
            offset: Количество результатов для пропуска
            category: Фильтр по категории документа (опционально)
            user_id: ID пользователя, владельца документов

        Returns:
            Последовательность кортежей (Document, relevance_score),
            где relevance_score - оценка релевантности документа запросу
        """
        ts_query = func.plainto_tsquery("russian", query).op("||")(func.plainto_tsquery("english", query))

        conditions = [
            Document.user_id == user_id,
            Document.is_archived.is_(False),
            Document.search_vector.op("@@")(ts_query),
        ]

        if category:
            conditions.append(Document.category == category)

        ts_rank = func.ts_rank(Document.search_vector, ts_query).label("relevance_score")

        result = await self.db.execute(
            select(Document, ts_rank).where(*conditions).order_by(ts_rank.desc()).limit(limit).offset(offset)
        )
        return [(row.Document, row.relevance_score) for row in result.all()]

    async def get_by_id_for_update(self, document_id: UUID, user_id: UUID) -> Document | None:
        """
        Получить документ по ID с блокировкой для обновления.

        Использует SELECT ... FOR UPDATE для предотвращения race conditions.

        Args:
            document_id: Уникальный идентификатор документа
            user_id: ID пользователя, владельца документа

        Returns:
            Объект Document или None если не найден или архивный
        """
        result: Document | None = await self.db.scalar(self._base_query(document_id, user_id).with_for_update())
        return result
