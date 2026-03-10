"""
API v2 для управления документами пользователей.

Модуль предоставляет эндпоинты для CRUD операций над документами:
- GET /documents — получение списка документов с курсорной пагинацией
- GET /documents/{id} — получение документа по ID
- POST /documents — создание нового документа
- PATCH /documents/{id} — обновление документа
- DELETE /documents/{id} — мягкое удаление документа

Все эндпоинты требуют аутентификации и возвращают данные только текущего пользователя.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.depends.db_depends import get_async_postgres_db
from app.depends.service_depends import get_document_service
from app.enum.documents import DocumentCategory
from app.exceptions import DocumentNotFoundError, InvalidCursorError
from app.models import User as UserModel
from app.models.documents import Document as DocumentModel
from app.schemas.documents import BaseResponse, DocumentCreate, DocumentResponse, DocumentSearchResponse, DocumentUpdate
from app.schemas.pagination import PaginatedResponse
from app.services.document_service import DocumentService
from app.utils.pagination import DEFAULT_OFFSET, DEFAULT_PER_PAGE, MINIMUM_PER_PAGE, paginate_with_cursor


router = APIRouter(prefix="/documents", tags=["Documents_v2"])


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="Получить документы пользователя с пагинацией",
)
async def get_all_documents(
    category: DocumentCategory | None = None,
    limit: int = Query(
        default=DEFAULT_PER_PAGE, ge=MINIMUM_PER_PAGE, description="Размер страницы (1-100). По умолчанию: 20"
    ),
    cursor: str | None = Query(
        default=None, description="Курсор для следующей страницы. Берётся из предыдущего ответа"
    ),
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
    include_archived: bool = Query(False, description="Включать неактивные документы"),
) -> PaginatedResponse[BaseResponse]:
    """
    Получить документы текущего пользователя с курсорной пагинацией.

    Args:
        category: Фильтр по категории документов (опционально)
        limit: Размер страницы (1-100)
        cursor: Курсор для следующей страницы
        include_archived: Включать ли неактивные (удалённые) документы
        current_user: Текущий аутентифицированный пользователь
        db: Сессия базы данных

    Returns:
        PaginatedResponse со списком документов и курсором для следующей страницы

    Raises:
        HTTPException 400: Невалидный формат курсора
    """
    logger.info(
        f"Запрос на получение документов пользователя {current_user.id} "
        f"с пагинацией: limit={limit}, cursor={'да' if cursor else 'нет'}"
    )

    # Формируем базовый запрос
    conditions = [DocumentModel.user_id == current_user.id]

    if category:
        conditions.append(DocumentModel.category == category)

    if not include_archived:
        conditions.append(DocumentModel.is_archived.is_(False))

    query = select(DocumentModel).where(*conditions)

    try:
        documents, next_cursor, has_next = await paginate_with_cursor(
            db=db,
            query=query,
            cursor=cursor,
            limit=limit,
            model=DocumentModel,
        )
    except InvalidCursorError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    logger.info(
        f"Возвращено {len(documents)} документов, has_next={has_next}, next_cursor={'да' if next_cursor else 'нет'}"
    )

    return PaginatedResponse(
        items=[BaseResponse.model_validate(document) for document in documents],
        next_cursor=next_cursor,
        has_next=has_next,
    )


@router.get("/search", status_code=status.HTTP_200_OK, summary="Поиск документов по тексту")
async def get_document_with_query(
    query: str,
    limit: int = Query(
        default=DEFAULT_PER_PAGE, ge=MINIMUM_PER_PAGE, description="Размер страницы (1-100). По умолчанию: 20"
    ),
    offset: int = Query(default=DEFAULT_OFFSET, ge=0, description="Смещение для пагинации"),
    category: DocumentCategory | None = None,
    current_user: UserModel = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
) -> DocumentSearchResponse:
    """
    Полнотекстовый поиск документов текущего пользователя.

    Выполняет поиск по содержимому документов с поддержкой русского и английского языков.
    Результаты сортируются по релевантности.

    Args:
        query: Поисковый запрос (текст)
        limit: Максимальное количество результатов (1-100)
        offset: Смещение для пагинации
        category: Фильтр по категории документа (опционально)
        current_user: Текущий аутентифицированный пользователь
        service:

    Returns:
        DocumentSearchResponse: Результаты поиска с оценками релевантности
    """
    logger.info(f"Поиск документов по запросу: '{query}' пользователя {current_user.id}")
    return await service.search_user_documents(query, limit, offset, category, current_user.id)


@router.get("/{document_id}", status_code=status.HTTP_200_OK, summary="Получить документ по ID")
async def get_document(
    document_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    """
    Получить документ по ID.

    Args:
        document_id: UUID документа
        current_user: Текущий аутентифицированный пользователь
        service:

    Returns:
        DocumentResponse: Данные запрошенного документа

    Raises:
        HTTPException 404: Если документ не найден или принадлежит другому пользователю
    """
    logger.info(f"Запрос на получение документа {document_id} пользователя {current_user.id}")

    try:
        return await service.get_user_document(document_id, current_user.id)

    except DocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.post("", status_code=status.HTTP_202_ACCEPTED, summary="Создать новый документ")
async def create_document(
    document_data: DocumentCreate,
    current_user: UserModel = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    """
    Создать новый документ пользователя.

    Args:
        document_data: Данные для создания документа
        current_user: Текущий аутентифицированный пользователь
        service:

    Returns:
        DocumentResponse: Данные созданного документа

    Raises:
        HTTPException 422: Некорректные данные документа
    """
    logger.info(f"Запрос на создание документа пользователем {current_user.id}")

    return await service.create_user_document(document_data, current_user.id)


@router.patch("/{document_id}", status_code=status.HTTP_202_ACCEPTED, summary="Обновить документ")
async def update_document(
    document_id: UUID,
    document_data: DocumentUpdate,
    current_user: UserModel = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    """
    Обновить документ пользователя

    Args:
        document_id: UUID документа для обновления
        document_data: Новые данные документа
        current_user: Текущий аутентифицированный пользователь
        service:

    Returns:
        DocumentResponse: Данные обновлённого документа

    Raises:
        HTTPException 404: Если документ не найден или принадлежит другому пользователю
    """
    logger.info(f"Запрос на обновление документа {document_id} пользователя {current_user.id}")

    try:
        return await service.update_user_document(document_id, document_data, current_user.id)

    except DocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить документ")
async def delete_document(
    document_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
) -> None:
    """
    Удалить документ (мягкое удаление).

    Документ помечается как архивированный (is_archived=True) и исключается
    из основного списка, но остаётся в базе данных.

    Args:
        document_id: UUID документа для удаления
        current_user: Текущий аутентифицированный пользователь
        service:

    Returns:
        None (HTTP 204 No Content)

    Raises:
        HTTPException 404: Если документ не найден или уже архивирован
    """
    logger.info(f"Запрос на удаление документа {document_id} пользователя {current_user.id}")

    try:
        await service.delete_user_document(document_id, current_user.id)

    except DocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
