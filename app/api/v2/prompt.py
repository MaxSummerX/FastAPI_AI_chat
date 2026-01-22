from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.depends.db_depends import get_async_postgres_db
from app.models.prompts import Prompts as PromptModel
from app.models.users import User as UserModel
from app.schemas.pagination import PaginatedResponse
from app.schemas.prompts import (
    PromptCreate,
    PromptResponse,
    PromptUpdate,
)
from app.utils.utils_for_pagination import (
    calculate_has_more,
    decode_cursor,
    encode_cursor,
    trim_excess_item,
    validate_pagination_limit,
)


router = APIRouter(prefix="/prompts", tags=["Prompts_v2"])

DEFAULT_PER_PAGE = 20
MINIMUM_PER_PAGE = 1
MAXIMUM_PER_PAGE = 100


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Получить промпты пользователя с пагинацией",
)
async def get_user_prompts(
    limit: int = Query(
        default=DEFAULT_PER_PAGE, ge=MINIMUM_PER_PAGE, description="Размер страницы (1-100). По умолчанию: 20"
    ),
    cursor: str | None = Query(
        default=None, description="Курсор для следующей страницы. Берётся из предыдущего ответа"
    ),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
    include_inactive: bool = Query(False, description="Включать неактивные промпты"),
) -> PaginatedResponse[PromptResponse]:
    """
    Получить промпты пользователя с пагинацией (курсорной).
    """
    logger.info(
        f"Запрос на получение промптов пользователя {current_user.id} "
        f"с пагинацией: limit={limit}, cursor={'да' if cursor else 'нет'}"
    )

    # Валидируем limit
    limit = validate_pagination_limit(limit, default=DEFAULT_PER_PAGE, maximum=MAXIMUM_PER_PAGE)

    # Базовое условие - промпты текущего пользователя
    conditions = [PromptModel.user_id == current_user.id]

    # Добавляем условие по активности, если не включаем неактивные
    if not include_inactive:
        conditions.append(PromptModel.is_active.is_(True))

    # Формируем базовый запрос
    query = select(PromptModel).where(*conditions)

    # Применяем курсор если указан
    if cursor:
        try:
            # Используем составной ключ (timestamp, id_uuid) для точного позиционирования
            timestamp, cursor_id_str = decode_cursor(cursor)
            id_uuid = UUID(cursor_id_str)

            query = query.where(
                (PromptModel.created_at < timestamp)
                | ((PromptModel.created_at == timestamp) & (PromptModel.id < id_uuid))
            )
            logger.debug(f"Применён курсор: timestamp={timestamp}, id={id_uuid}")
        except ValueError as e:
            logger.warning(f"Невалидный курсор от пользователя {current_user.id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid cursor format: {str(e)}"
            ) from None

    # Используем составную сортировку для стабильности результатов
    query = query.order_by(PromptModel.created_at.desc(), PromptModel.id.desc())

    # Берём на один элемент больше для проверки has_next
    result = await db.scalars(query.limit(limit + 1))
    prompts = list(result.all())

    # Проверяем наличие следующей страницы
    has_next = calculate_has_more(prompts, limit)

    # Убираем лишний элемент если он есть
    prompts = trim_excess_item(prompts, limit, reverse=False)

    # Формируем курсор для следующей страницы
    next_cursor = None

    if prompts and has_next:
        last_prompt = prompts[-1]
        next_cursor = encode_cursor(last_prompt.created_at, last_prompt.id)
        logger.debug(f"Сформирован курсор для следующей страницы на основе промпта {last_prompt.id}")

    logger.info(
        f"Возвращено {len(prompts)} промптов, has_next={has_next}, next_cursor={'да' if next_cursor else 'нет'}"
    )

    return PaginatedResponse(
        items=[PromptResponse.model_validate(prompt) for prompt in prompts],
        next_cursor=next_cursor,
        has_next=has_next,
    )


@router.get("/{prompt_id}", status_code=status.HTTP_200_OK, summary="Получить промпт по ID")
async def get_prompt(
    prompt_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> PromptResponse:
    """Получить конкретный промпт"""
    logger.info(f"Запрос на получение промпта {prompt_id} пользователем {current_user.id}")

    result = await db.scalars(
        select(PromptModel).where(
            PromptModel.id == prompt_id, PromptModel.user_id == current_user.id, PromptModel.is_active.is_(True)
        )
    )

    prompt = result.first()
    if not prompt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Промпт не найден или недоступен")

    return PromptResponse.model_validate(prompt)


@router.post("", status_code=status.HTTP_201_CREATED, summary="Создать новый промпт")
async def create_prompt(
    prompt_data: PromptCreate,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> PromptResponse:
    """Создать новый промпт"""
    logger.info(f"Запрос на создание промпта пользователем {current_user.id}")

    prompt = PromptModel(
        user_id=current_user.id, title=prompt_data.title, content=prompt_data.content, metadata_=prompt_data.metadata_
    )

    db.add(prompt)
    await db.commit()
    await db.refresh(prompt)

    logger.info(f"Промпт {prompt.id} успешно создан")
    return PromptResponse.model_validate(prompt)


@router.put("/{prompt_id}", status_code=status.HTTP_200_OK, summary="Обновить промпт")
async def update_prompt(
    prompt_id: UUID,
    prompt_data: PromptUpdate,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> PromptResponse:
    """Обновить промпт"""
    logger.info(f"Запрос на обновление промпта {prompt_id} пользователем {current_user.id}")

    # Находим промпт
    result = await db.scalars(
        select(PromptModel).where(PromptModel.id == prompt_id, PromptModel.user_id == current_user.id)
    )

    prompt = result.first()
    if not prompt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Промпт не найден")

    # Обновляем только переданные поля
    if prompt_data.title is not None:
        prompt.title = prompt_data.title
    if prompt_data.content is not None:
        prompt.content = prompt_data.content
    if prompt_data.metadata_ is not None:
        prompt.metadata_ = prompt_data.metadata_
    if prompt_data.is_active is not None:
        prompt.is_active = prompt_data.is_active

    await db.commit()
    await db.refresh(prompt)

    logger.info(f"Промпт {prompt.id} успешно обновлен")
    return PromptResponse.model_validate(prompt)


@router.delete("/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить промпт")
async def delete_prompt(
    prompt_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> None:
    """
    Удалить промпт (мягкое удаление)
    """
    logger.info(f"Запрос на удаление промпта {prompt_id} пользователем {current_user.id}")

    # Находим промпт
    result = await db.scalars(
        select(PromptModel).where(
            PromptModel.id == prompt_id, PromptModel.user_id == current_user.id, PromptModel.is_active.is_(True)
        )
    )

    prompt = result.first()
    if not prompt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Промпт не найден или уже удален")

    # Мягкое удаление - меняем флаг is_active
    prompt.is_active = False
    await db.commit()

    logger.info(f"Промпт {prompt.id} успешно удален")
