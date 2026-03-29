"""
Репозитории документов.

Интерфейсы для работы с документами в соответствии с принципами clean architecture.
Определяют контракт для CRUD операций, пагинации и полнотекстового поиска.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from app.domain.enums.document import DocumentCategory
from app.domain.models.document import Document


class IDocumentRepository(ABC):
    """
    Интерфейс репозитория для работы с документами.

    Определяет контракт для управления документами пользователей:
    создание, обновление, пагинация и полнотекстовый поиск.
    """

    @abstractmethod
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

        Args:
            user_id: ID пользователя, владельца документов
            cursor: Курсор из предыдущего ответа для следующей страницы
            limit: Максимальное количество документов на странице
            category: Фильтр по категории документа (опционально)
            include_archived: Включать ли архивные документы в результаты

        Returns:
            Кортеж (документы, следующий_курсор, есть_ли_следующая_страница)
        """
        pass

    @abstractmethod
    async def get_by_id(self, document_id: UUID, user_id: UUID) -> Document | None:
        """
        Получить документ по ID.

        Args:
            document_id: Уникальный идентификатор документа
            user_id: ID пользователя, владельца документа

        Returns:
            Объект Document или None, если документ не найден
        """
        pass

    @abstractmethod
    async def create(
        self,
        user_id: UUID,
        title: str,
        content: str,
        category: DocumentCategory,
        metadata_: dict | None,
        tags: dict | None,
    ) -> Document:
        """
        Создать новый документ.

        Args:
            user_id: ID пользователя, владельца документа
            title: Заголовок документа
            content: Содержимое документа
            category: Категория документа из DocumentCategory
            metadata_: Дополнительные метаданные в формате JSON (опционально)
            tags: Теги для организации документов (опционально)

        Returns:
            Созданный объект Document
        """
        pass

    @abstractmethod
    async def save(self, document: Document) -> Document:
        """
        Сохранить изменения документа.

        Args:
            document: Объект Document с обновлёнными данными

        Returns:
            Сохранённый объект Document
        """
        pass

    @abstractmethod
    async def search(
        self,
        query: str,
        limit: int,
        offset: int,
        category: DocumentCategory | None,
        user_id: UUID,
    ) -> Sequence[Document]:
        """
        Полнотекстовый поиск по документам пользователя.

        Args:
            query: Поисковый запрос (текст для поиска)
            limit: Максимальное количество результатов
            offset: Количество результатов для пропуска
            category: Фильтр по категории документа (опционально)
            user_id: ID пользователя, владельца документов

        Returns:
            Последовательность найденных документов
        """
        pass

    @abstractmethod
    async def get_by_id_for_update(self, user_id: UUID, document_id: UUID) -> Document | None:
        """
        Получить документ по ID с блокировкой для обновления.

        Используется для предотвращения race conditions при параллельных обновлениях.

        Args:
            user_id: ID пользователя, владельца документа
            document_id: Уникальный идентификатор документа

        Returns:
            Объект Document или None, если документ не найден
        """
        pass
