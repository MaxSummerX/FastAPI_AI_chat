from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from loguru import logger
from mem0 import AsyncMemory
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.fact import FactCreate, FactResponse
from app.application.schemas.pagination import PaginatedResponse
from app.depends.mem0_depends import get_memory
from app.domain.models.fact import Fact as FactModel
from app.domain.models.fact import FactCategory, FactSource
from app.domain.models.user import User as UserModel
from app.infrastructure.database.dependencies import get_db
from app.infrastructure.persistence.pagination import (
    DEFAULT_PER_PAGE,
    MINIMUM_PER_PAGE,
    InvalidCursorError,
    paginate_with_cursor,
)
from app.presentation.dependencies import get_current_user
from app.services.fact_service import (
    FactNotFoundException,
    UserProvidedException,
    create_user_fact,
    get_fact_or_404_or_403,
    import_from_mem0ai_to_postgres_db,
    update_user_fact,
)


router = APIRouter(prefix="/facts", tags=["Facts_v2"])


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Получить факты пользователя с пагинацией",
)
async def get_all_facts(
    category: FactCategory | None = None,
    source_type: FactSource | None = None,
    limit: int = Query(
        default=DEFAULT_PER_PAGE, ge=MINIMUM_PER_PAGE, description="Размер страницы (1-100). По умолчанию: 20"
    ),
    cursor: str | None = Query(
        default=None, description="Курсор для следующей страницы. Берётся из предыдущего ответа"
    ),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    include_inactive: bool = Query(False, description="Включать неактивные факты"),
) -> PaginatedResponse[FactResponse]:
    """
    Получить факты текущего пользователя с курсорной пагинацией.

    Args:
        category: Фильтр по категории факта (опционально)
        source_type: Фильтр по источнику факта (опционально)
        limit: Размер страницы (1-100)
        cursor: Курсор для следующей страницы
        include_inactive: Включать ли неактивные (удалённые) факты
        current_user: Текущий аутентифицированный пользователь
        db: Сессия базы данных

    Returns:
        PaginatedResponse со списком фактов и курсором для следующей страницы

    Raises:
        HTTPException 400: Невалидный формат курсора
    """
    logger.info(
        f"Запрос на получение фактов пользователя {current_user.id} "
        f"с пагинацией: limit={limit}, cursor={'да' if cursor else 'нет'}"
    )

    # Формируем базовый запрос
    conditions = [FactModel.user_id == current_user.id]

    if category:
        conditions.append(FactModel.category == category)

    if source_type:
        conditions.append(FactModel.source_type == source_type)

    if not include_inactive:
        conditions.append(FactModel.is_active.is_(True))

    query = select(FactModel).where(*conditions)

    try:
        facts, next_cursor, has_next = await paginate_with_cursor(
            db=db,
            query=query,
            cursor=cursor,
            limit=limit,
            model=FactModel,
        )
    except InvalidCursorError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None

    logger.info(f"Возвращено {len(facts)} фактов, has_next={has_next}, next_cursor={'да' if next_cursor else 'нет'}")

    return PaginatedResponse(
        items=[FactResponse.model_validate(fact) for fact in facts],
        next_cursor=next_cursor,
        has_next=has_next,
    )


@router.get("/{fact_id}", status_code=status.HTTP_200_OK, summary="Получить факт по ID")
async def get_fact(
    fact_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FactResponse:
    """
    Получить факт по ID.

    Args:
        fact_id: UUID факта
        current_user: Текущий аутентифицированный пользователь
        db: Сессия базы данных

    Returns:
        FactResponse: Данные запрошенного факта

    Raises:
        HTTPException 404: Если факт не найден или принадлежит другому пользователю
    """
    logger.info(f"Запрос на получение факта {fact_id} пользователя {current_user.id}")
    result = await db.scalars(
        select(FactModel).where(
            FactModel.id == fact_id, FactModel.user_id == current_user.id, FactModel.is_active.is_(True)
        )
    )

    fact = result.first()

    if not fact:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found")

    return FactResponse.model_validate(fact)


@router.post("", status_code=status.HTTP_202_ACCEPTED, summary="Создать новый факт")
async def create_fact(
    fact_data: FactCreate,
    background_tasks: BackgroundTasks,
    memory: AsyncMemory = Depends(get_memory),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Создать новый факт о пользователе.

    Факт создаётся асинхронно в фоне:
    1. Добавляется в Qdrant (через mem0ai без связей в Neo4j)
    2. Сохраняется в PostgreSQL с mem0_id

    Args:
        fact_data: Данные для создания факта
        background_tasks: FastAPI background tasks
        memory: Экземпляр AsyncMemory из mem0ai
        current_user: Текущий аутентифицированный пользователь
        db: Сессия базы данных

    Returns:
        dict[str, Any]: Статус обработки (processing)

    Raises:
        HTTPException 422: Некорректные данные факта
    """
    logger.info(f"Запрос на создание факта пользователем {current_user.id}")

    background_tasks.add_task(create_user_fact, fact_data, memory, current_user, db)

    return {"status": "processing", "message": "Факт добавляется", "content": fact_data.content}


@router.put("/{fact_id}", status_code=status.HTTP_202_ACCEPTED, summary="Обновить факт")
async def update_fact(
    fact_id: UUID,
    fact_data: FactCreate,
    background_tasks: BackgroundTasks,
    memory: AsyncMemory = Depends(get_memory),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Полностью обновить факт (PostgreSQL + Qdrant).

    Обновление происходит асинхронно в фоне:
    1. Удаляет старый вектор из Qdrant
    2. Создаёт новый вектор в Qdrant
    3. Обновляет запись в PostgreSQL

    Args:
        fact_id: UUID факта для обновления
        fact_data: Новые полные данные факта
        background_tasks: FastAPI background tasks
        memory: Экземпляр AsyncMemory из mem0ai
        current_user: Текущий аутентифицированный пользователь
        db: Сессия базы данных

    Returns:
        dict[str, Any]: Статус обработки (processing)

    Raises:
        HTTPException 404: Если факт не найден или принадлежит другому пользователю
    """
    logger.info(f"Запрос на обновление факта {fact_id} пользователя {current_user.id}")

    try:
        fact = await get_fact_or_404_or_403(fact_id, current_user.id, db)

        background_tasks.add_task(update_user_fact, fact, fact_data, memory, current_user, db)
        return {"status": "processing", "message": "Факт обновляется", "content": fact_data.content}

    except FactNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except UserProvidedException as e:
        raise HTTPException(status_code=403, detail=str(e)) from None


@router.delete("/{fact_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить факт")
async def delete_fact(
    fact_id: UUID,
    memory: AsyncMemory = Depends(get_memory),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Удалить факт (мягкое удаление).

    Факт помечается как неактивный (is_active=False) и удаляется из Qdrant.

    Args:
        fact_id: UUID факта для удаления
        memory: Экземпляр AsyncMemory из mem0ai
        current_user: Текущий аутентифицированный пользователь
        db: Сессия базы данных

    Returns:
        None (HTTP 204 No Content)

    Raises:
        HTTPException 404: Если факт не найден или неактивен
        HTTPException 403: Если факт не USER_PROVIDED (нельзя удалять EXTRACTED)
    """
    try:
        logger.info(f"Запрос на удаление факта {fact_id} пользователя {current_user.id}")
        fact = await get_fact_or_404_or_403(fact_id, current_user.id, db)

        await db.execute(update(FactModel).where(FactModel.id == fact_id).values(is_active=False))
        await db.commit()

        if fact.mem0_id:
            await memory.delete(memory_id=str(fact.mem0_id))

        logger.info(f"Удален факт {fact_id}")

    except FactNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except UserProvidedException as e:
        raise HTTPException(status_code=403, detail=str(e)) from None


@router.post("/import_facts", status_code=status.HTTP_202_ACCEPTED, summary="Импортировать факты")
async def import_facts(
    background_tasks: BackgroundTasks,
    current_user: UserModel = Depends(get_current_user),
    memory: AsyncMemory = Depends(get_memory),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Импортировать факты из mem0ai в PostgreSQL.

    Импортирует все EXTRACTED факты из Qdrant/mem0ai в PostgreSQL.
    Процесс выполняется асинхронно в фоне:
    1. Получает факты с source_type=EXTRACTED из mem0ai
    2. Проверяет существующие факты в PostgreSQL
    3. Создаёт новые записи для неимпортированных фактов

    Args:
        background_tasks: FastAPI background tasks
        current_user: Текущий аутентифицированный пользователь
        memory: Экземпляр AsyncMemory из mem0ai
        db: Сессия базы данных

    Returns:
        dict[str, str]: Статус обработки (processing)
    """
    background_tasks.add_task(import_from_mem0ai_to_postgres_db, current_user.id, memory, db)

    return {"status": "processing"}
