from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.depends.db_depends import get_async_postgres_db
from app.models.prompts import Prompts as PromptModel
from app.models.users import User as UserModel
from app.schemas.prompts import (
    PromptCreate,
    PromptListResponse,
    PromptResponse,
    PromptUpdate,
)


router_v1 = APIRouter(prefix="/prompts", tags=["Prompts"])


@router_v1.get("/", response_model=PromptListResponse, status_code=status.HTTP_200_OK)
async def get_user_prompts(
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
    page: int = Query(1, ge=1, description="Номер страницы"),
    size: int = Query(10, ge=1, le=100, description="Размер страницы"),
    include_inactive: bool = Query(False, description="Включать неактивные промпты"),
) -> PromptListResponse:
    """Получить все промпты пользователя"""
    logger.info(f"Запрос на получение промптов пользователя {current_user.id}")

    # Базовое условие - промпты текущего пользователя
    conditions = [PromptModel.user_id == current_user.id]

    # Добавляем условие по активности, если не включаем неактивные
    if not include_inactive:
        conditions.append(PromptModel.is_active.is_(True))

    # Считаем общее количество
    count_result = await db.scalar(select(func.count()).select_from(PromptModel).where(*conditions))
    total = count_result or 0

    # Получаем промпты с пагинацией
    result = await db.scalars(
        select(PromptModel)
        .where(*conditions)
        .order_by(PromptModel.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )

    prompts = cast(list[PromptModel], result.all())

    return PromptListResponse(
        prompts=[PromptResponse.model_validate(prompt) for prompt in prompts], total=total, page=page, size=size
    )


@router_v1.get("/{prompt_id}", response_model=PromptResponse, status_code=status.HTTP_200_OK)
async def get_prompt(
    prompt_id: str,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> PromptModel:
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

    return cast(PromptModel, prompt)


@router_v1.post("/", response_model=PromptResponse, status_code=status.HTTP_201_CREATED)
async def create_prompt(
    prompt_data: PromptCreate,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> PromptModel:
    """Создать новый промпт"""
    logger.info(f"Запрос на создание промпта пользователем {current_user.id}")

    prompt = PromptModel(
        user_id=current_user.id, title=prompt_data.title, content=prompt_data.content, metadata_=prompt_data.metadata_
    )

    db.add(prompt)
    await db.commit()
    await db.refresh(prompt)

    logger.info(f"Промпт {prompt.id} успешно создан")
    return prompt


@router_v1.put("/{prompt_id}", response_model=PromptResponse, status_code=status.HTTP_200_OK)
async def update_prompt(
    prompt_id: str,
    prompt_data: PromptUpdate,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> PromptModel:
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
    return cast(PromptModel, prompt)


@router_v1.delete("/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt(
    prompt_id: str,
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
