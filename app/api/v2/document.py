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
from app.enum.documents import DocumentCategory
from app.models import User as UserModel
from app.models.documents import Document as DocumentModel
from app.schemas.documents import BaseResponse, DocumentCreate, DocumentResponse, DocumentSearchResponse, DocumentUpdate
from app.schemas.pagination import PaginatedResponse
from app.services.document_service import (
    DocumentNotFoundError,
    create_user_document,
    delete_user_document,
    get_user_document,
    search_user_documents,
    update_user_document,
)
from app.utils.utils_for_pagination import (
    calculate_has_more,
    decode_cursor,
    encode_cursor,
    trim_excess_item,
    validate_pagination_limit,
)


router = APIRouter(prefix="/documents", tags=["Documents_v2"])

DEFAULT_PER_PAGE = 20
MINIMUM_PER_PAGE = 1
MAXIMUM_PER_PAGE = 100
DEFAULT_OFFSET = 0


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

    # Валидируем limit
    limit = validate_pagination_limit(limit, default=DEFAULT_PER_PAGE, maximum=MAXIMUM_PER_PAGE)

    # Формируем базовый запрос

    conditions = [DocumentModel.user_id == current_user.id]

    if category:
        conditions.append(DocumentModel.category == category)

    if not include_archived:
        conditions.append(DocumentModel.is_archived.is_(False))

    query = select(DocumentModel).where(*conditions)

    # Применяем курсор если указан
    if cursor:
        try:
            # Используем составной ключ (timestamp, id_uuid) для точного позиционирования
            timestamp, cursor_id_str = decode_cursor(cursor)
            id_uuid = UUID(cursor_id_str)

            query = query.where(
                (DocumentModel.created_at < timestamp)
                | ((DocumentModel.created_at == timestamp) & (DocumentModel.id < id_uuid))
            )
            logger.debug(f"Применён курсор: timestamp={timestamp}, id={id_uuid}")
        except ValueError as e:
            logger.warning(f"Невалидный курсор от пользователя {current_user.id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid cursor format: {str(e)}"
            ) from None

    # Используем составную сортировку для стабильности результатов
    query = query.order_by(DocumentModel.created_at.desc(), DocumentModel.id.desc())

    # Берём на один элемент больше для проверки has_next
    result = await db.scalars(query.limit(limit + 1))
    documents = list(result.all())

    # Проверяем наличие следующей страницы
    has_next = calculate_has_more(documents, limit)

    # Убираем лишний элемент если он есть
    documents = trim_excess_item(documents, limit, reverse=False)

    # Формируем курсор для следующей страницы
    next_cursor = None

    if documents and has_next:
        last_document = documents[-1]
        next_cursor = encode_cursor(last_document.created_at, last_document.id)
        logger.debug(f"Сформирован курсор для следующей страницы на основе документа {last_document.id}")

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
    db: AsyncSession = Depends(get_async_postgres_db),
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
        db: Сессия базы данных

    Returns:
        DocumentSearchResponse: Результаты поиска с оценками релевантности
    """
    logger.info(f"Поиск документов по запросу: '{query}' пользователя {current_user.id}")
    return await search_user_documents(query, limit, offset, category, current_user.id, db)


@router.get("/{document_id}", status_code=status.HTTP_200_OK, summary="Получить документ по ID")
async def get_document(
    document_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> DocumentResponse:
    """
    Получить документ по ID.

    Args:
        document_id: UUID документа
        current_user: Текущий аутентифицированный пользователь
        db: Сессия базы данных

    Returns:
        DocumentResponse: Данные запрошенного документа

    Raises:
        HTTPException 404: Если документ не найден или принадлежит другому пользователю
    """
    logger.info(f"Запрос на получение документа {document_id} пользователя {current_user.id}")

    try:
        return await get_user_document(document_id, current_user, db)

    except DocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.post("", status_code=status.HTTP_202_ACCEPTED, summary="Создать новый документ")
async def create_document(
    document_data: DocumentCreate,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> DocumentResponse:
    """
    Создать новый документ пользователя.

    Args:
        document_data: Данные для создания документа
        current_user: Текущий аутентифицированный пользователь
        db: Сессия базы данных

    Returns:
        DocumentResponse: Данные созданного документа

    Raises:
        HTTPException 422: Некорректные данные документа
    """
    logger.info(f"Запрос на создание документа пользователем {current_user.id}")

    return await create_user_document(document_data, current_user, db)


@router.patch("/{document_id}", status_code=status.HTTP_202_ACCEPTED, summary="Обновить документ")
async def update_document(
    document_id: UUID,
    document_data: DocumentUpdate,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> DocumentResponse:
    """
    Обновить документ пользователя

    Args:
        document_id: UUID документа для обновления
        document_data: Новые данные документа
        current_user: Текущий аутентифицированный пользователь
        db: Сессия базы данных

    Returns:
        DocumentResponse: Данные обновлённого документа

    Raises:
        HTTPException 404: Если документ не найден или принадлежит другому пользователю
    """
    logger.info(f"Запрос на обновление документа {document_id} пользователя {current_user.id}")

    try:
        return await update_user_document(document_id, document_data, current_user, db)

    except DocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить документ")
async def delete_document(
    document_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> None:
    """
    Удалить документ (мягкое удаление).

    Документ помечается как архивированный (is_archived=True) и исключается
    из основного списка, но остаётся в базе данных.

    Args:
        document_id: UUID документа для удаления
        current_user: Текущий аутентифицированный пользователь
        db: Сессия базы данных

    Returns:
        None (HTTP 204 No Content)

    Raises:
        HTTPException 404: Если документ не найден или уже архивирован
    """
    logger.info(f"Запрос на удаление документа {document_id} пользователя {current_user.id}")

    try:
        await delete_user_document(document_id, current_user, db)

    except DocumentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
