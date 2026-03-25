"""
SQLAlchemy реализация репозитория пользователей.

Конкретная реализация IUserRepository для персистентности User сущности
через SQLAlchemy async engine. Следует интерфейсу из domain слоя.
"""

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models.user import User
from app.domain.repositories.users import IUserRepository


class UserSQLAlchemyRepository(IUserRepository):
    """
    SQLAlchemy реализация репозитория пользователей.

    Предоставляет CRUD операции для User сущности через SQLAlchemy async.
    Все запросы фильтруют неактивных пользователей (is_active=False).
    """

    def __init__(self, db: AsyncSession):
        """
        Инициализирует репозиторий.

        Args:
            db: Асинхронная сессия SQLAlchemy
        """
        self.db = db

    async def get_by_id(self, user_id: UUID) -> User | None:
        """
        Получить пользователя по ID.

        Args:
            user_id: Уникальный идентификатор пользователя

        Returns:
            Объект User или None если не найден или неактивен
        """
        result: User | None = await self.db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
        return result

    async def get_by_username(self, username: str) -> User | None:
        """
        Получить пользователя по username.

        Args:
            username: Имя пользователя

        Returns:
            Объект User или None если не найден или неактивен
        """
        result: User | None = await self.db.scalar(
            select(User).where(User.username == username, User.is_active.is_(True))
        )
        return result

    async def get_by_email(self, email: str) -> User | None:
        """
        Получить пользователя по email.

        Args:
            email: Email адрес

        Returns:
            Объект User или None если не найден или неактивен
        """
        result: User | None = await self.db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
        return result

    async def get_by_email_or_username(self, identifier: str) -> User | None:
        """
        Получить пользователя по email или username.

        Удобно для логина когда пользователь может ввести либо email, либо username.

        Args:
            identifier: Email или username

        Returns:
            Объект User или None если не найден или неактивен
        """
        result: User | None = await self.db.scalar(
            select(User).where(or_(User.username == identifier, User.email == identifier), User.is_active.is_(True)),
        )
        return result

    async def save(self, user: User) -> User:
        """
        Сохранить изменения пользователя.

        Args:
            user: Объект User с изменёнными данными

        Returns:
            Обновлённый объект User из БД
        """
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def create(self, username: str, email: str, password_hash: str) -> User:
        """
        Создать нового пользователя.

        Args:
            username: Имя пользователя
            email: Email адрес
            password_hash: Хэш пароля

        Returns:
            Созданный объект User с присвоенным ID
        """
        new_user = User(username=username, email=email, password_hash=password_hash)
        self.db.add(new_user)
        await self.db.commit()
        await self.db.refresh(new_user)
        return new_user

    async def is_username_unique(self, username: str, exclude_id: UUID | None = None) -> bool:
        """
        Проверить уникальность username.

        Args:
            username: Имя пользователя для проверки
            exclude_id: Исключить пользователя из проверки (для обновления)

        Returns:
            True если username уникален, False если уже занят
        """
        query = select(User).where(User.username == username)
        if exclude_id:
            query = query.where(User.id != exclude_id)
        result = await self.db.scalar(query)
        return result is None

    async def is_email_unique(self, email: str, exclude_id: UUID | None = None) -> bool:
        """
        Проверить уникальность email.

        Args:
            email: Email для проверки
            exclude_id: Исключить пользователя из проверки (для обновления)

        Returns:
            True если email уникален, False если уже занят
        """
        query = select(User).where(User.email == email)
        if exclude_id:
            query = query.where(User.id != exclude_id)
        result = await self.db.scalar(query)
        return result is None

    async def get_verified_active_user(self, user_id: UUID) -> User | None:
        """
        Получить верифицированного активного пользователя.

        Дополнительно проверяет is_verified флаг.

        Args:
            user_id: Уникальный идентификатор пользователя

        Returns:
            Объект User или None если не найден, неактивен или неверифицирован
        """
        result: User | None = await self.db.scalar(
            select(User).where(User.id == user_id, User.is_active.is_(True), User.is_verified.is_(True))
        )
        return result

    async def count_active_users(self) -> int:
        """
        Посчитать количество активных пользователей.

        Returns:
            Количество пользователей с is_active=True
        """
        result = await self.db.scalar(select(func.count(User.id)).where(User.is_active.is_(True)))
        return result if result else 0

    async def get_by_id_for_update(self, user_id: UUID) -> User | None:
        """
        Получить пользователя с блокировкой для обновления.

        Использует SELECT ... FOR UPDATE для предотвращения race conditions.
        Применяется когда нужно обновить данные с гарантией, что они не изменились.

        Args:
            user_id: Уникальный идентификатор пользователя

        Returns:
            Объект User или None если не найден или неактивен
        """
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.is_active.is_(True)).with_for_update()
        )
        user: User | None = result.scalar_one_or_none()
        return user
