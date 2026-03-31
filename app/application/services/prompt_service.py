from uuid import UUID

from loguru import logger

from app.application.exceptions.prompt import PromptNotFoundError
from app.application.schemas.pagination import PaginatedResponse
from app.application.schemas.prompt import PromptCreate, PromptResponse, PromptUpdate
from app.domain.repositories.prompts import IPromptRepository


class PromptService:
    """Сервис для управления промптами пользователей."""

    def __init__(self, prompt_repo: IPromptRepository) -> None:
        """
        Инициализирует сервис промптов.

        Args:
            prompt_repo: Репозиторий промптов для доступа к данным
        """
        self.prompt_repo = prompt_repo

    async def get_user_prompts(
        self, limit: int, cursor: str | None, user_id: UUID, include_inactive: bool
    ) -> PaginatedResponse[PromptResponse]:
        """
        Получить промпты пользователя с курсорной пагинацией.

        Args:
            limit: Максимальное количество промптов на странице
            cursor: Курсор из предыдущего ответа для следующей страницы
            user_id: UUID пользователя
            include_inactive: Включать ли неактивные промпты

        Returns:
            PaginatedResponse с промптами и метаданными пагинации
        """
        logger.debug(
            "Запрос на получение промптов пользователя {} с пагинацией: limit={}, cursor={}",
            user_id,
            limit,
            "да" if cursor else "нет",
        )

        prompts, next_cursor, has_next = await self.prompt_repo.get_paginated(
            user_id=user_id, cursor=cursor, limit=limit, include_inactive=include_inactive
        )

        logger.debug(
            "Возвращено {} промптов, has_next={}, next_cursor={}",
            len(prompts),
            has_next,
            "да" if next_cursor else "нет",
        )

        return PaginatedResponse(
            items=[PromptResponse.model_validate(prompt) for prompt in prompts],
            next_cursor=next_cursor,
            has_next=has_next,
        )

    async def get_user_prompt(
        self,
        prompt_id: UUID,
        user_id: UUID,
    ) -> PromptResponse:
        """
        Получить промпт пользователя по ID.

        Выполняет поиск промпта с проверкой прав доступа.
        Возвращает только активные промпты текущего пользователя.

        Args:
            prompt_id: UUID искомого промпта
            user_id: UUID пользователя

        Returns:
            PromptResponse: Данные найденного промпта

        Raises:
            PromptNotFoundError: Если промпт не найден, принадлежит другому
                пользователю или неактивен
        """
        logger.debug("Запрос на получение промпта {} пользователя {}", prompt_id, user_id)
        prompt = await self.prompt_repo.get_by_id(prompt_id=prompt_id, user_id=user_id)

        if not prompt:
            logger.warning("Промпт не найден: prompt_id={}, user_id={}", prompt_id, user_id)
            raise PromptNotFoundError(f"Prompt {prompt_id} not found")

        return PromptResponse.model_validate(prompt)

    async def create_prompt(
        self,
        prompt_data: PromptCreate,
        user_id: UUID,
    ) -> PromptResponse:
        """
        Создать новый промпт для пользователя.

        Создаёт промпт с указанными параметрами и сохраняет его в базу данных.

        Args:
            prompt_data: Данные для создания промпта (заголовок, содержимое, метаданные)
            user_id: UUID пользователя

        Returns:
            PromptResponse: Данные созданного промпта с присвоенным UUID
        """
        logger.debug("Запрос на создание промпта пользователем {}", user_id)

        prompt = await self.prompt_repo.create(
            user_id=user_id, title=prompt_data.title, content=prompt_data.content, metadata_=prompt_data.metadata_
        )

        logger.debug("Создан промпт {} для пользователя {}", prompt.id, user_id)

        return PromptResponse.model_validate(prompt)

    async def update_prompt(
        self,
        prompt_id: UUID,
        prompt_data: PromptUpdate,
        user_id: UUID,
    ) -> PromptResponse:
        """
        Обновить данные существующего промпта.

        Выполняет частичное обновление промпта - обновляются только переданные поля.
        Проверяет право доступа перед изменением. Если данные для обновления не переданы,
        возвращает текущее состояние промпта.

        Args:
            prompt_id: UUID обновляемого промпта
            prompt_data: Данные для обновления (частичные - только изменяемые поля)
            user_id: UUID пользователя

        Returns:
            PromptResponse: Обновлённые данные промпта

        Raises:
            PromptNotFoundError: Если промпт не найден или принадлежит другому пользователю
        """
        logger.debug("Запрос на обновление промпта {} пользователем {}", prompt_id, user_id)

        prompt = await self.prompt_repo.get_by_id_for_update(prompt_id=prompt_id, user_id=user_id)

        if not prompt:
            logger.warning("Промпт не найден: prompt_id={}, user_id={}", prompt_id, user_id)
            raise PromptNotFoundError(f"Prompt {prompt_id} not found")

        update_data = prompt_data.model_dump(exclude_unset=True, by_alias=False)

        if not update_data:
            return PromptResponse.model_validate(prompt)

        for field, value in update_data.items():
            setattr(prompt, field, value)

        result = await self.prompt_repo.save(prompt)

        logger.debug("Промпт {} успешно обновлен", prompt.id)
        return PromptResponse.model_validate(result)

    async def soft_delete_user_prompt(self, prompt_id: UUID, user_id: UUID) -> None:
        """
        Удалить промпт (мягкое удаление).

        Промпт помечается как неактивный (is_active=False) и исключается
        из основного списка, но остаётся в базе данных. Мягкое удаление позволяет
        восстановить промпт при необходимости.

        Args:
            prompt_id: UUID удаляемого промпта
            user_id: UUID пользователя

        Returns:
            None

        Raises:
            PromptNotFoundError: Если промпт не найден, уже неактивен
                или принадлежит другому пользователю

        Note:
            Функция выполняет мягкое удаление - промпт физически остаётся
            в базе данных, но помечается как is_active=False
        """
        logger.debug("Запрос на удаление промпта {} пользователем {}", prompt_id, user_id)

        prompt = await self.prompt_repo.get_by_id_for_update(prompt_id=prompt_id, user_id=user_id)

        if not prompt:
            logger.warning("Промпт не найден: prompt_id={}, user_id={}", prompt_id, user_id)
            raise PromptNotFoundError(f"Prompt {prompt_id} not found")

        prompt.is_active = False

        await self.prompt_repo.save(prompt)

        logger.debug("Промпт {} успешно удален", prompt.id)
