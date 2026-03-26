from uuid import UUID

from loguru import logger

from app.application.exceptions.user import (
    EmailAlreadyExistsException,
    IncorrectPasswordException,
    SameEmailException,
    SamePasswordException,
    SameUsernameException,
    UserAlreadyAdminException,
    UsernameAlreadyExistsException,
    UserNotFoundException,
)
from app.application.schemas.user import UserResponseBase, UserResponseFull, UserUpdateProfile
from app.domain.enums.role import UserRole
from app.domain.repositories.users import IUserRepository
from app.infrastructure.security import hash_password, verify_password


class UserService:
    """Сервис для управления профилями пользователей."""

    def __init__(self, user_repo: IUserRepository):
        """
        Инициализирует сервис пользователей.

        Args:
            user_repo: Репозиторий пользователей для доступа к данным
        """
        self.user_repo = user_repo

    async def get_base_profile(self, user_id: UUID) -> UserResponseBase:
        """
        Получить базовую информацию о пользователе.

        Args:
            user_id: UUID пользователя

        Returns:
            Базовые данные пользователя

        Raises:
            UserNotFoundException: Если пользователь не найден
        """
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundException("User not found")
        return UserResponseBase.model_validate(user)

    async def get_full_profile(self, user_id: UUID) -> UserResponseFull:
        """
        Получить полную информацию о пользователе.

        Args:
            user_id: UUID пользователя

        Returns:
            Полные данные пользователя

        Raises:
            UserNotFoundException: Если пользователь не найден
        """
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise UserNotFoundException("User not found")
        return UserResponseFull.model_validate(user)

    async def update_user_profile(self, user_id: UUID, user_data: UserUpdateProfile) -> UserResponseFull:
        """
        Обновить дополнительные данные профиля пользователя.

        Args:
            user_id: UUID пользователя
            user_data: Данные для обновления (только не-None поля)

        Returns:
            Обновлённые данные пользователя

        Raises:
            UserNotFoundException: Если пользователь не найден
        """
        user = await self.user_repo.get_by_id_for_update(user_id)
        if not user:
            raise UserNotFoundException("User not found")

        # Формируем словарь с обновлениями (только не-None поля)
        update_data = user_data.model_dump(exclude_unset=True, by_alias=False)

        if not update_data:
            # Нет данных для обновления
            return UserResponseFull.model_validate(user)

        # Применяем обновления
        for field, value in update_data.items():
            setattr(user, field, value)

        result = await self.user_repo.save(user)

        return UserResponseFull.model_validate(result)

    async def update_email(self, user_id: UUID, new_email: str, current_password: str) -> UserResponseBase:
        """
        Обновить email пользователя.

        Требуется текущий пароль для подтверждения.

        Args:
            user_id: UUID пользователя
            new_email: Новый email
            current_password: Текущий пароль для подтверждения

        Returns:
            Обновлённые данные пользователя

        Raises:
            UserNotFoundException: Если пользователь не найден
            IncorrectPasswordException: Если неверный текущий пароль
            SameEmailException: Если новый email совпадает с текущим
            EmailAlreadyExistsException: Если новый email уже занят
        """
        user = await self.user_repo.get_by_id_for_update(user_id)
        if not user:
            raise UserNotFoundException("User not found")

        # 1. Проверяем текущий пароль
        if not verify_password(current_password, str(user.password_hash)):
            logger.warning("Неверный пароль при попытке обновления email для: {}", user_id)
            raise IncorrectPasswordException("Incorrect current password")

        # 2. Проверяем что новый email отличается от текущего
        if new_email == user.email:
            logger.warning("Попытка обновить email на уже занятый: {}", user_id)
            raise SameEmailException("Email matches current")

        # 3. Проверяем что новый email уникален
        await self._validate_user_unique(str(user.username), new_email, exclude_user_id=user_id)

        # 4. Обновляем email
        user.email = new_email
        result = await self.user_repo.save(user)

        return UserResponseBase.model_validate(result)

    async def update_username(self, user_id: UUID, new_username: str, current_password: str) -> UserResponseBase:
        """
        Обновить username пользователя.

        Требуется текущий пароль для подтверждения.

        Args:
            user_id: UUID пользователя
            new_username: Новый username
            current_password: Текущий пароль для подтверждения

        Returns:
            Обновлённые данные пользователя

        Raises:
            UserNotFoundException: Если пользователь не найден
            IncorrectPasswordException: Если неверный текущий пароль
            SameUsernameException: Если новый username совпадает с текущим
            UsernameAlreadyExistsException: Если новый username уже занят
        """
        user = await self.user_repo.get_by_id_for_update(user_id)
        if not user:
            raise UserNotFoundException("User not found")

        # 1. Проверяем текущий пароль
        if not verify_password(current_password, str(user.password_hash)):
            logger.warning("Неверный пароль при попытке обновления username: {}", user_id)
            raise IncorrectPasswordException("Incorrect current password")

        # 2. Проверяем что новый username отличается от текущего
        if new_username == user.username:
            logger.warning("Новый username совпадает с текущим: {}", user_id)
            raise SameUsernameException("username matches current")

        # 3. Проверяем что новый username уникален
        await self._validate_user_unique(new_username, str(user.email), exclude_user_id=user_id)

        # 4. Обновляем username
        user.username = new_username
        result = await self.user_repo.save(user)

        return UserResponseBase.model_validate(result)

    async def change_password(self, user_id: UUID, old_password: str, new_password: str) -> UserResponseBase:
        """
        Изменить пароль пользователя.

        Требуется текущий пароль для подтверждения.

        Args:
            user_id: UUID пользователя
            old_password: Текущий пароль для подтверждения
            new_password: Новый пароль

        Returns:
            Обновлённые данные пользователя

        Raises:
            UserNotFoundException: Если пользователь не найден
            IncorrectPasswordException: Если неверный текущий пароль
            SamePasswordException: Если новый пароль совпадает с текущим
        """
        user = await self.user_repo.get_by_id_for_update(user_id)
        if not user:
            raise UserNotFoundException("User not found")

        # 1. Проверяем что old_password совпадает с тем что бд
        if not verify_password(old_password, str(user.password_hash)):
            logger.warning("Неверный пароль при попытке обновления пароля: {}", user_id)
            raise IncorrectPasswordException("Incorrect current password")

        # 2. Проверяем что new_password пароль отличается от текущего
        if verify_password(new_password, str(user.password_hash)):
            logger.warning("Новый пароль совпадает с текущим: {}", user_id)
            raise SamePasswordException("New password is the same as the current password")

        # 3. Хешируем новый пароль
        user.password_hash = hash_password(new_password)
        # 4. Обновляем пароль
        result = await self.user_repo.save(user)

        return UserResponseBase.model_validate(result)

    async def _validate_user_unique(
        self,
        username: str,
        email: str,
        exclude_user_id: UUID | None = None,
    ) -> None:
        """
        Проверяет уникальность username и email.

        Args:
            username: Имя пользователя для проверки
            email: Email для проверки
            exclude_user_id: ID пользователя для исключения из проверки
                            (используется при обновлении профиля)

        Raises:
            UsernameAlreadyExistsException: Если username уже занят
            EmailAlreadyExistsException: Если email уже занят
        """
        if not await self.user_repo.is_username_unique(username, exclude_user_id):
            logger.warning("Username уже занят: {}", username)
            raise UsernameAlreadyExistsException("Username already taken")

        # Проверка уникальности email
        if not await self.user_repo.is_email_unique(email, exclude_user_id):
            logger.warning("email уже занят: {}", email)
            raise EmailAlreadyExistsException("Email already registered")

    async def promote_to_admin(self, user_id: UUID) -> UserResponseFull:
        """
        Повысить пользователя до роли администратора.

        Args:
            user_id: UUID пользователя для повышения

        Returns:
            Обновлённые данные пользователя

        Raises:
            UserNotFoundException: Если пользователь не найден
            UserAlreadyAdminException: Если пользователь уже администратор
        """
        user = await self.user_repo.get_verified_active_user(user_id)
        if not user:
            logger.warning("Попытка повысить несуществующего юзера: {}", user_id)
            raise UserNotFoundException("User not found")

        if user.role == UserRole.ADMIN:
            logger.warning("Юзер уже админ: {}", user_id)
            raise UserAlreadyAdminException("User is already an admin")

        user.role = UserRole.ADMIN
        await self.user_repo.save(user)
        logger.info("Пользователь {} повышен до роли -> admin", user_id)
        return UserResponseFull.model_validate(user)

    async def active_users(self) -> int:
        """
        Получить количество активных пользователей.

        Returns:
            Количество активных пользователей
        """
        return await self.user_repo.count_active_users()
