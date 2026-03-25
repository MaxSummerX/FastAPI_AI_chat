"""
Репозитории пользователей.

Интерфейсы для работы с пользователями в соответствии с принципами clean architecture.
Определяют контракт для CRUD операций и валидации данных.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.models.user import User


class IUserRepository(ABC):
    """
    Интерфейс репозитория для работы с пользователями.

    Определяет контракт для выполнения CRUD операций над пользователями
    и проверки уникальности идентификаторов (username, email).
    """

    @abstractmethod
    async def get_by_id(self, user_id: UUID) -> User | None:
        """
        Получить пользователя по ID.

        Args:
            user_id: Уникальный идентификатор пользователя

        Returns:
            Объект User или None, если пользователь не найден
        """
        pass

    @abstractmethod
    async def get_by_username(self, username: str) -> User | None:
        """
        Получить пользователя по username.

        Args:
            username: Имя пользователя

        Returns:
            Объект User или None, если пользователь не найден
        """
        pass

    @abstractmethod
    async def get_by_email(self, email: str) -> User | None:
        """
        Получить пользователя по email.

        Args:
            email: Email адрес

        Returns:
            Объект User или None, если пользователь не найден
        """
        pass

    @abstractmethod
    async def get_by_email_or_username(self, identifier: str) -> User | None:
        """
        Получить пользователя по email или username.

        Args:
            identifier: Email или username

        Returns:
            Объект User или None, если пользователь не найден
        """
        pass

    @abstractmethod
    async def save(self, user: User) -> User:
        """
        Сохранить изменения пользователя.

        Args:
            user: Объект User с обновлёнными данными

        Returns:
            Сохранённый объект User
        """
        pass

    @abstractmethod
    async def create(self, username: str, email: str, password_hash: str) -> User:
        """
        Создать нового пользователя.

        Args:
            username: Имя пользователя
            email: Email адрес
            password_hash: Хеш пароля

        Returns:
            Созданный объект User
        """
        pass

    # Валидация
    @abstractmethod
    async def is_username_unique(self, username: str, exclude_id: UUID | None = None) -> bool:
        """
        Проверить уникальность username.

        Args:
            username: Имя пользователя для проверки
            exclude_id: ID пользователя для исключения из проверки
                        (используется при обновлении профиля)

        Returns:
            True, если username уникален, иначе False
        """
        pass

    @abstractmethod
    async def is_email_unique(self, email: str, exclude_id: UUID | None = None) -> bool:
        """
        Проверить уникальность email.

        Args:
            email: Email для проверки
            exclude_id: ID пользователя для исключения из проверки
                        (используется при обновлении профиля)

        Returns:
            True, если email уникален, иначе False
        """
        pass

    @abstractmethod
    async def get_verified_active_user(self, user_id: UUID) -> User | None:
        """
        Получить верифицированного активного пользователя.

        Args:
            user_id: Уникальный идентификатор пользователя

        Returns:
            Объект User или None, если пользователь не найден/неактивен/не верифицирован
        """
        pass

    @abstractmethod
    async def count_active_users(self) -> int:
        """
        Получить количество активных пользователей.

        Returns:
            Число активных пользователей
        """
        pass

    @abstractmethod
    async def get_by_id_for_update(self, user_id: UUID) -> User | None:
        """
        Получить пользователя по ID с блокировкой для обновления.

        Используется для предотвращения race conditions при параллельных обновлениях.

        Args:
            user_id: Уникальный идентификатор пользователя

        Returns:
            Объект User или None, если пользователь не найден
        """
        pass
