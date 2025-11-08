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


router_v1 = APIRouter(prefix="/facts", tags=["Facts"])


@router_v1.get("/", response_model=list[FactResponse], status_code=status.HTTP_200_OK)
async def get_all_facts(
    category: FactCategory | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> list[FactModel]:
    """
    Получить все факты о пользователе
    """
    logger.info(f"Запрос на получение фактов пользователя {current_user.id} (category={category}, limit={limit})")

    query = select(FactModel).where(FactModel.user_id == current_user.id, FactModel.is_active.is_(True))

    if category:
        query = query.where(FactModel.category == category)

    query = query.order_by(FactModel.created_at.desc())
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)

    facts = cast(list[FactModel], result.scalars().all())
    return facts


@router_v1.get("/{memory_id}", response_model=FactResponse, status_code=status.HTTP_200_OK)
async def get_fact(
    memory_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> FactModel:
    """
    Получить один факт о пользователе
    """
    logger.info(f"Запрос на получение факта {memory_id} пользователя {current_user.id}")
    result = await db.scalars(
        select(FactModel).where(
            FactModel.id == memory_id, FactModel.user_id == current_user.id, FactModel.is_active.is_(True)
        )
    )

    fact = cast(FactModel, result.first())

    if not fact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found")

    return fact


@router_v1.post("/", response_model=FactResponse, status_code=status.HTTP_201_CREATED)
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


@router_v1.patch("/{memory_id}", response_model=FactResponse, status_code=status.HTTP_200_OK)
async def update_fact(
    memory_id: UUID,
    fact_data: FactUpdate,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> FactModel:
    """
    Обновить факт о пользователе
    """
    logger.info(f"Запрос на обновление факта {memory_id} пользователя {current_user.id}")
    result = await db.execute(
        update(FactModel)
        .where(FactModel.id == memory_id, FactModel.user_id == current_user.id, FactModel.is_active.is_(True))
        .values(**fact_data.model_dump(exclude_unset=True, by_alias=False))
        .returning(FactModel)
    )

    fact = result.scalar_one_or_none()

    if not fact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found")

    await db.commit()

    logger.info(f"Обновлён факт {memory_id}")

    return cast(FactModel, fact)


@router_v1.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fact(
    memory_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> None:
    """
    Мягкое удаление факта
    """
    logger.info(f"Запрос на удаление факта {memory_id} пользователя {current_user.id}")
    result = await db.execute(
        update(FactModel)
        .where(FactModel.id == memory_id, FactModel.user_id == current_user.id, FactModel.is_active.is_(True))
        .values(is_active=False)
        .returning(FactModel.id)
    )

    deleted_fact = result.scalar_one_or_none()

    if not deleted_fact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found")

    await db.commit()

    logger.info(f"Удалён факт {memory_id}")
