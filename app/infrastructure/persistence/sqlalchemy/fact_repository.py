"""
SQLAlchemy реализация репозитория фактов.

Конкретная реализация IFactRepository для персистентности Fact сущности
через SQLAlchemy async engine. Следует интерфейсу из domain слоя.
Поддерживает курсорную пагинацию и фильтрацию по категории и источнику.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums.fact import FactCategory, FactSource
from app.domain.models.fact import Fact
from app.domain.repositories.facts import IFactRepository
from app.infrastructure.persistence.pagination import paginate_with_cursor


class FactsSQLAlchemyRepository(IFactRepository):
    """
    SQLAlchemy реализация репозитория фактов.

    Предоставляет CRUD операции для Fact сущности через SQLAlchemy async.
    Поддерживает курсорную пагинацию и фильтрацию по категории и источнику.
    """

    def __init__(self, db: AsyncSession):
        """
        Инициализирует репозиторий.

        Args:
            db: Асинхронная сессия SQLAlchemy
        """
        self.db = db

    async def get_paginated(
        self,
        user_id: UUID,
        cursor: str | None,
        limit: int,
        category: FactCategory | None = None,
        source: FactSource | None = None,
        include_archived: bool = False,
    ) -> tuple[Sequence[Fact], str | None, bool]:
        """
        Получить факты пользователя с курсорной пагинацией.

        Поддерживает фильтрацию по категории, источнику и статусу архивации.
        По умолчанию архивированные факты исключаются.

        Args:
            user_id: ID пользователя
            cursor: Курсор из предыдущего ответа для следующей страницы
            limit: Максимальное количество фактов на странице
            category: Фильтр по категории факта
            source: Фильтр по источнику факта
            include_archived: Включать ли архивные факты

        Returns:
            Кортеж (факты, следующий_курсор, есть_ли_следующая_страница)
        """
        conditions = [Fact.user_id == user_id]

        if category:
            conditions.append(Fact.category == category)

        if source:
            conditions.append(Fact.source_type == source)

        if not include_archived:
            conditions.append(Fact.is_active.is_(True))

        query = select(Fact).where(*conditions)

        facts, next_cursor, has_next = await paginate_with_cursor(
            db=self.db,
            query=query,
            cursor=cursor,
            limit=limit,
            model=Fact,
        )
        return facts, next_cursor, has_next

    async def get_by_id(self, fact_id: UUID, user_id: UUID) -> Fact | None:
        """
        Получить факт по идентификатору.

        Возвращает только активные (не архивированные) факты.

        Args:
            fact_id: ID факта
            user_id: ID пользователя (для проверки владения)

        Returns:
            Объект Fact или None, если не найден
        """
        result: Fact | None = await self.db.scalar(
            select(Fact).where(Fact.id == fact_id, Fact.user_id == user_id, Fact.is_active.is_(True))
        )
        return result

    async def create(
        self,
        user_id: UUID,
        content: str,
        category: FactCategory,
        source_type: FactSource,
        confidence: float,
        source_conversation_id: UUID | None = None,
        source_message_id: UUID | None = None,
        superseded_by_id: UUID | None = None,
        metadata_: dict | None = None,
        mem0_id: UUID | None = None,
    ) -> Fact:
        """
        Создать новый факт.

        Args:
            user_id: ID пользователя, которому принадлежит факт
            content: Содержание факта
            category: Категория факта
            source_type: Источник факта
            confidence: Уровень уверенности (0.0-1.0)
            source_conversation_id: ID беседы-источника
            source_message_id: ID сообщения-источника
            superseded_by_id: ID факта, которым заменён данный
            metadata_: Дополнительные метаданные
            mem0_id: ID факта во внешней системе памяти

        Returns:
            Созданный объект Fact с присвоенным ID
        """
        fact = Fact(
            user_id=user_id,
            content=content,
            category=category,
            source_type=source_type,
            confidence=confidence,
            source_conversation_id=source_conversation_id,
            source_message_id=source_message_id,
            superseded_by_id=superseded_by_id,
            metadata_=metadata_,
            mem0_id=mem0_id,
        )

        self.db.add(fact)
        await self.db.commit()
        await self.db.refresh(fact)

        return fact

    async def update(self, fact_id: UUID, update_data: dict) -> None:
        """
        Обновить данные факта.

        Args:
            fact_id: ID факта для обновления
            update_data: Словарь с обновляемыми полями

        Raises:
            Exception: При ошибке выполнения запроса
        """
        try:
            await self.db.execute(update(Fact).where(Fact.id == fact_id).values(**update_data))
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

    async def get_all_facts_by_source(self, user_id: UUID, source: FactSource) -> Sequence[Fact]:
        """
        Получить все факты пользователя по источнику.

        Args:
            user_id: ID пользователя
            source: Источник факта для фильтрации

        Returns:
            Последовательность фактов указанного источника
        """
        results = await self.db.scalars(select(Fact).where(Fact.user_id == user_id, Fact.source_type == source))
        all_res: Sequence[Fact] = results.all()
        return all_res

    async def save(self, fact: Fact) -> Fact:
        """
        Сохранить Changeset факта в базу.

        Args:
            fact: Объект Fact для сохранения

        Returns:
            Обновлённый объект Fact

        Raises:
            Exception: При ошибке коммита
        """
        try:
            await self.db.commit()
            await self.db.refresh(fact)
            return fact
        except Exception:
            await self.db.rollback()
            raise

    async def save_all(self, facts: Sequence[Fact]) -> bool:
        """
        Сохранить пакет фактов в базу.

        Args:
            facts: Последовательность фактов для сохранения

        Returns:
            True если все факты сохранены успешно

        Raises:
            Exception: При ошибке коммита
        """
        try:
            self.db.add_all(facts)
            await self.db.commit()
            return True
        except Exception:
            await self.db.rollback()
            raise

    async def get_existing_facts(self, source: FactSource, content: list[str]) -> Sequence[Fact]:
        """
        Получить существующие факты по источнику и содержанию.

        Args:
            source: Источник факта для фильтрации
            content: Список содержаний для поиска

        Returns:
            Последовательность найденных фактов
        """
        existing_facts: Sequence[Fact] = (
            await self.db.scalars(select(Fact).where(Fact.content.in_(content), Fact.source_type == source))
        ).all()
        return existing_facts
