from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger

from app.application.exceptions.document import DocumentNotFoundError
from app.application.schemas.document import (
    BaseResponse,
    DocumentCreate,
    DocumentResponse,
    DocumentSearchResponse,
    DocumentUpdate,
)
from app.application.schemas.pagination import PaginatedResponse
from app.application.services.document_service import DocumentService
from app.domain.enums.document import DocumentCategory
from app.domain.models.user import User as UserModel
from app.infrastructure.persistence.pagination import (
    DEFAULT_OFFSET,
    DEFAULT_PER_PAGE,
    MINIMUM_PER_PAGE,
    InvalidCursorError,
)
from app.presentation.dependencies import get_current_user, get_document_service


router = APIRouter(prefix="/documents", tags=["Documents"])


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
    include_archived: bool = Query(False, description="Включать неактивные документы"),
    current_user: UserModel = Depends(get_current_user),
    service: DocumentService = Depends(get_document_service),
) -> PaginatedResponse[BaseResponse]:
    """
    Получить документы текущего пользователя с курсорной пагинацией.

    Args:
        category: Фильтр по категории документов (опционально)
        limit: Размер страницы (1-100)
        cursor: Курсор для следующей страницы
        include_archived: Включать ли неактивные (удалённые) документы
        current_user: Текущий аутентифицированный пользователь
        service: Сервис документов для бизнес-логики

    Returns:
        PaginatedResponse со списком документов и курсором для следующей страницы

    Raises:
        HTTPException 400: Невалидный формат курсора
    """
    try:
        return await service.get_user_documents(
            category=category,
            limit=limit,
            cursor=cursor,
            user_id=current_user.id,
            include_archived=include_archived,
        )

    except InvalidCursorError as e:
        logger.warning("Невалидный курсор пользователя {}: {}", current_user.id, str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from None


@router.get("/search", status_code=status.HTTP_200_OK, summary="Поиск документов по тексту")
async def search_documents(
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
        service: Сервис документов для бизнес-логики

    Returns:
        DocumentSearchResponse: Результаты поиска с оценками релевантности
    """
    return await service.search_user_documents(
        query=query,
        limit=limit,
        offset=offset,
        category=category,
        current_user_id=current_user.id,
    )


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
        service: Сервис документов для бизнес-логики

    Returns:
        DocumentResponse: Данные запрошенного документа

    Raises:
        HTTPException 404: Если документ не найден или принадлежит другому пользователю
    """

    try:
        return await service.get_user_document(document_id=document_id, current_user_id=current_user.id)

    except DocumentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


@router.post("", status_code=status.HTTP_201_CREATED, summary="Создать новый документ")
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
        service: Сервис документов для бизнес-логики

    Returns:
        DocumentResponse: Данные созданного документа

    Raises:
        HTTPException 422: Некорректные данные документа
    """
    return await service.create_user_document(document_data=document_data, current_user_id=current_user.id)


@router.patch("/{document_id}", status_code=status.HTTP_200_OK, summary="Обновить документ")
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
        service: Сервис документов для бизнес-логики

    Returns:
        DocumentResponse: Данные обновлённого документа

    Raises:
        HTTPException 404: Если документ не найден или принадлежит другому пользователю
    """
    try:
        return await service.update_user_document(
            document_id=document_id, document_data=document_data, current_user_id=current_user.id
        )

    except DocumentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None


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
        service: Сервис документов для бизнес-логики

    Returns:
        None (HTTP 204 No Content)

    Raises:
        HTTPException 404: Если документ не найден или уже архивирован
    """
    try:
        await service.soft_delete_user_document(document_id=document_id, current_user_id=current_user.id)

    except DocumentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from None
