from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.depends.db_depends import get_async_postgres_db
from app.models import Fact as FactModel
from app.models import User as UserModel
from app.models.facts import FactCategory, FactSource
from app.schemas.facts import FactCreate, FactResponse, FactUpdate
from app.schemas.pagination import PaginatedResponse
from app.utils.utils_for_pagination import (
    calculate_has_more,
    decode_cursor,
    encode_cursor,
    trim_excess_item,
    validate_pagination_limit,
)


router = APIRouter(prefix="/facts", tags=["Facts_v2"])

DEFAULT_PER_PAGE = 20
MINIMUM_PER_PAGE = 1
MAXIMUM_PER_PAGE = 100


@router.get(
    "/",
    response_model=PaginatedResponse[FactResponse],
    status_code=status.HTTP_200_OK,
    summary="Получить факты пользователя с пагинацией",
)
async def get_all_facts(
    category: FactCategory | None = None,
    limit: int = Query(
        default=DEFAULT_PER_PAGE, ge=MINIMUM_PER_PAGE, description="Размер страницы (1-100). По умолчанию: 20"
    ),
    cursor: str | None = Query(
        default=None, description="Курсор для следующей страницы. Берётся из предыдущего ответа"
    ),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
    include_inactive: bool = Query(False, description="Включать неактивные факты"),
) -> PaginatedResponse[FactResponse]:
    """
    Получить факты пользователя с пагинацией (курсорной).
    """
    logger.info(
        f"Запрос на получение фактов пользователя {current_user.id} "
        f"с пагинацией: limit={limit}, cursor={'да' if cursor else 'нет'}"
    )

    # Валидируем limit
    limit = validate_pagination_limit(limit, default=DEFAULT_PER_PAGE, maximum=MAXIMUM_PER_PAGE)

    # Формируем базовый запрос

    conditions = [FactModel.user_id == current_user.id]

    if category:
        conditions.append(FactModel.category == category)

    if not include_inactive:
        conditions.append(FactModel.is_active.is_(True))

    query = select(FactModel).where(*conditions)

    # Применяем курсор если указан
    if cursor:
        try:
            # Используем составной ключ (timestamp, id_uuid) для точного позиционирования
            timestamp, cursor_id_str = decode_cursor(cursor)
            id_uuid = UUID(cursor_id_str)

            query = query.where(
                (FactModel.created_at < timestamp) | ((FactModel.created_at == timestamp) & (FactModel.id < id_uuid))
            )
            logger.debug(f"Применён курсор: timestamp={timestamp}, id={id_uuid}")
        except ValueError as e:
            logger.warning(f"Невалидный курсор от пользователя {current_user.id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid cursor format: {str(e)}"
            ) from None

    # Используем составную сортировку для стабильности результатов
    query = query.order_by(FactModel.created_at.desc(), FactModel.id.desc())

    # Берём на один элемент больше для проверки has_next
    result = await db.scalars(query.limit(limit + 1))
    facts = list(result.all())

    # Проверяем наличие следующей страницы
    has_next = calculate_has_more(facts, limit)

    # Убираем лишний элемент если он есть
    facts = trim_excess_item(facts, limit, reverse=False)

    # Формируем курсор для следующей страницы
    next_cursor = None

    if facts and has_next:
        last_fact = facts[-1]
        next_cursor = encode_cursor(last_fact.created_at, last_fact.id)
        logger.debug(f"Сформирован курсор для следующей страницы на основе факта {last_fact.id}")

    logger.info(f"Возвращено {len(facts)} фактов, has_next={has_next}, next_cursor={'да' if next_cursor else 'нет'}")

    return PaginatedResponse(
        items=cast(list[FactResponse], facts),
        next_cursor=next_cursor,
        has_next=has_next,
    )


@router.get("/{fact_id}", response_model=FactResponse, status_code=status.HTTP_200_OK, summary="Получить факт по ID")
async def get_fact(
    fact_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> FactModel:
    """
    Получить один факт о пользователе
    """
    logger.info(f"Запрос на получение факта {fact_id} пользователя {current_user.id}")
    result = await db.scalars(
        select(FactModel).where(
            FactModel.id == fact_id, FactModel.user_id == current_user.id, FactModel.is_active.is_(True)
        )
    )

    fact = cast(FactModel, result.first())

    if not fact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found")

    return fact


@router.post("/", response_model=FactResponse, status_code=status.HTTP_201_CREATED, summary="Создать новый факт")
async def create_fact(
    fact_data: FactCreate,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> FactModel:
    """
    Создание факта пользователем вручную.
    """
    logger.info(f"Запрос на создание факта пользователем {current_user.id}")
    category = fact_data.category
    if category is None:
        category = FactCategory.PERSONAL

    new_fact = FactModel(
        user_id=current_user.id,
        content=fact_data.content,
        category=category,
        source_type=FactSource.USER_PROVIDED,
        confidence=fact_data.confidence,
        metadata_=fact_data.metadata_,
    )

    db.add(new_fact)
    await db.commit()
    await db.refresh(new_fact)

    logger.info(f"Создан факт {new_fact.id} для пользователя {current_user.id}")

    return cast(FactModel, new_fact)


@router.patch("/{fact_id}", response_model=FactResponse, status_code=status.HTTP_200_OK, summary="Обновить факт")
async def update_fact(
    fact_id: UUID,
    fact_data: FactUpdate,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> FactModel:
    """
    Обновить факт о пользователе
    """
    logger.info(f"Запрос на обновление факта {fact_id} пользователя {current_user.id}")
    result = await db.execute(
        update(FactModel)
        .where(FactModel.id == fact_id, FactModel.user_id == current_user.id, FactModel.is_active.is_(True))
        .values(**fact_data.model_dump(exclude_unset=True, by_alias=False))
        .returning(FactModel)
    )

    fact = result.scalar_one_or_none()

    if not fact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found")

    await db.commit()

    logger.info(f"Обновлён факт {fact_id}")

    return cast(FactModel, fact)


@router.delete("/{fact_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить факт")
async def delete_fact(
    fact_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> None:
    """
    Мягкое удаление факта
    """
    logger.info(f"Запрос на удаление факта {fact_id} пользователя {current_user.id}")
    result = await db.execute(
        update(FactModel)
        .where(FactModel.id == fact_id, FactModel.user_id == current_user.id, FactModel.is_active.is_(True))
        .values(is_active=False)
        .returning(FactModel.id)
    )

    deleted_fact = result.scalar_one_or_none()

    if not deleted_fact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found")

    await db.commit()

    logger.info(f"Удалён факт {fact_id}")
