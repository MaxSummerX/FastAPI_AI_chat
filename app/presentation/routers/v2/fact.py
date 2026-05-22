from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from loguru import logger

from app.application.exceptions.fact import FactNotFoundException, UserProvidedException
from app.application.schemas.fact import FactCreate, FactResponse
from app.application.schemas.pagination import PaginatedResponse
from app.application.services.fact_service import FactService
from app.domain.models.fact import FactCategory, FactSource
from app.domain.models.user import User as UserModel
from app.infrastructure.persistence.pagination import (
    DEFAULT_PER_PAGE,
    MINIMUM_PER_PAGE,
    InvalidCursorError,
)
from app.presentation.dependencies import get_current_user, get_fact_service


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
    include_inactive: bool = Query(False, description="Включать неактивные факты"),
    current_user: UserModel = Depends(get_current_user),
    fact_service: FactService = Depends(get_fact_service),
) -> PaginatedResponse[FactResponse]:
    """
    Возвращает факты текущего пользователя с курсорной пагинацией.

    **Возможные ошибки:**
    - `400` — невалидный формат курсора
    """
    logger.info(
        f"Запрос на получение фактов пользователя {current_user.id} "
        f"с пагинацией: limit={limit}, cursor={'да' if cursor else 'нет'}"
    )
    try:
        return await fact_service.get_user_facts(
            user_id=current_user.id,
            cursor=cursor,
            limit=limit,
            category=category,
            source=source_type,
            include_archived=include_inactive,
        )

    except InvalidCursorError as e:
        logger.warning("Невалидный курсор пользователя {}: {}", current_user.id, str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


@router.get("/{fact_id}", status_code=status.HTTP_200_OK, summary="Получить факт по ID")
async def get_fact(
    fact_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    fact_service: FactService = Depends(get_fact_service),
) -> FactResponse:
    """
    Возвращает факт по ID.

    **Возможные ошибки:**
    - `404` — факт не найден или принадлежит другому пользователю
    """
    try:
        return await fact_service.get_user_fact_by_id(fact_id, current_user.id)
    except FactNotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.post("", status_code=status.HTTP_202_ACCEPTED, summary="Создать новый факт")
async def create_fact(
    fact_data: FactCreate,
    background_tasks: BackgroundTasks,
    current_user: UserModel = Depends(get_current_user),
    fact_service: FactService = Depends(get_fact_service),
) -> dict[str, Any]:
    """
    Создаёт новый факт о пользователе.

    Факт создаётся асинхронно в фоне:
    1. Добавляется в Qdrant (через mem0ai без связей в Neo4j)
    2. Сохраняется в PostgreSQL с mem0_id

    **Возможные ошибки:**
    - `422` — некорректные данные факта
    """
    logger.info(f"Запрос на создание факта пользователем {current_user.id}")

    background_tasks.add_task(fact_service.create_user_fact, current_user.id, fact_data)

    return {"status": "processing", "message": "Факт добавляется", "content": fact_data.content}


@router.put("/{fact_id}", status_code=status.HTTP_200_OK, summary="Обновить факт")
async def update_fact(
    fact_id: UUID,
    fact_data: FactCreate,
    current_user: UserModel = Depends(get_current_user),
    fact_service: FactService = Depends(get_fact_service),
) -> dict[str, Any]:
    """
    Полностью обновляет факт (PostgreSQL + Qdrant).

    Обновление происходит асинхронно в фоне:
    1. Удаляет старый вектор из Qdrant
    2. Создаёт новый вектор в Qdrant
    3. Обновляет запись в PostgreSQL

    **Возможные ошибки:**
    - `404` — факт не найден или принадлежит другому пользователю
    - `403` — факт не является USER_PROVIDED (нельзя редактировать EXTRACTED)
    """
    logger.info(f"Запрос на обновление факта {fact_id} пользователя {current_user.id}")

    try:
        await fact_service.update_user_fact(current_user.id, fact_id, fact_data)
        return {"status": "processing", "message": "Факт обновляется", "content": fact_data.content}

    except FactNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except UserProvidedException as e:
        raise HTTPException(status_code=403, detail=str(e)) from None


@router.delete("/{fact_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить факт")
async def delete_fact(
    fact_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    fact_service: FactService = Depends(get_fact_service),
) -> None:
    """
    Удаляет факт (мягкое удаление).

    Факт помечается как неактивный (is_active=False) и удаляется из Qdrant.

    **Возможные ошибки:**
    - `404` — факт не найден или неактивен
    - `403` — факт не является USER_PROVIDED (нельзя удалять EXTRACTED)
    """
    logger.info(f"Запрос на удаление факта {fact_id} пользователя {current_user.id}")
    try:
        await fact_service.delete_user_fact(fact_id, current_user.id)

    except FactNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except UserProvidedException as e:
        raise HTTPException(status_code=403, detail=str(e)) from None


@router.post("/import_facts", status_code=status.HTTP_202_ACCEPTED, summary="Импортировать факты")
async def import_facts(
    background_tasks: BackgroundTasks,
    current_user: UserModel = Depends(get_current_user),
    fact_service: FactService = Depends(get_fact_service),
) -> dict[str, str]:
    """
    Импортирует факты из mem0ai в PostgreSQL.

    Импортирует все EXTRACTED факты из Qdrant/mem0ai в PostgreSQL.
    Процесс выполняется асинхронно в фоне:
    1. Получает факты с source_type=EXTRACTED из mem0ai
    2. Проверяет существующие факты в PostgreSQL
    3. Создаёт новые записи для неимпортированных фактов
    """
    background_tasks.add_task(fact_service.import_from_mem0ai_to_postgres_db, current_user.id)

    return {"status": "processing"}
