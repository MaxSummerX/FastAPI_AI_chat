"""
Сервисный слой для управления документами пользователей.

Модуль предоставляет CRUD операции для работы с документами:
- Создание новых документов с категоризацией и тегами
- Получение документов с проверкой прав доступа
- Обновление содержимого и метаданных документов
- Мягкое удаление документов с возможностью восстановления

Все операции выполняются с проверкой прав доступа текущего пользователя
и поддерживают мягкое удаление через флаг is_archived.
"""

from uuid import UUID

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User as UserModel
from app.models.documents import Document as DocumentModel
from app.schemas.documents import DocumentCreate, DocumentResponse, DocumentUpdate


class DocumentNotFoundError(Exception):
    """
    Исключение, возникающее когда документ не найден или недоступен пользователю.
    """

    pass


async def get_user_document(document_id: UUID, current_user: UserModel, db: AsyncSession) -> DocumentResponse:
    """
    Получить документ пользователя по ID.

    Выполняет поиск документа с проверкой прав доступа и статуса архива.
    Возвращает только активные (не архивированные) документы текущего пользователя.

    Args:
        document_id: UUID искомого документа
        current_user: Текущий аутентифицированный пользователь
        db: Асинхронная сессия базы данных

    Returns:
        DocumentResponse: Данные найденного документа

    Raises:
        DocumentNotFoundError: Если документ не найден, принадлежит другому
            пользователю или архивирован
    """
    result = await db.scalars(
        select(DocumentModel).where(
            DocumentModel.id == document_id,
            DocumentModel.user_id == current_user.id,
            DocumentModel.is_archived.is_(False),
        )
    )

    document = result.first()

    if not document:
        raise DocumentNotFoundError(f"Document {document_id} not found")

    return DocumentResponse.model_validate(document)


async def create_user_document(
    document_data: DocumentCreate, current_user: UserModel, db: AsyncSession
) -> DocumentResponse:
    """
    Создать новый документ для пользователя.

    Создаёт документ с указанными параметрами и сохраняет его в базу данных.
    Категория документа по умолчанию устанавливается в NOTE.

    Args:
        document_data: Данные для создания документа (заголовок, содержимое,
            категория, теги, метаданные)
        current_user: Текущий аутентифицированный пользователь - владелец документа
        db: Асинхронная сессия базы данных

    Returns:
        DocumentResponse: Данные созданного документа с присвоенным UUID
    """
    document = DocumentModel(
        user_id=current_user.id,
        title=document_data.title,
        content=document_data.content,
        metadata_=document_data.metadata_,
        category=document_data.category,
        tags=document_data.tags,
    )

    db.add(document)
    await db.commit()
    await db.refresh(document)

    logger.info(f"Документ {document.id} успешно создан")
    return DocumentResponse.model_validate(document)


async def update_user_document(
    document_id: UUID, document_data: DocumentUpdate, current_user: UserModel, db: AsyncSession
) -> DocumentResponse:
    """
    Обновить данные существующего документа.

    Выполняет частичное обновление документа - обновляются только переданные поля.
    Проверяет право доступа перед изменением. Если данные для обновления не переданы,
    возвращает текущее состояние документа.

    Args:
        document_id: UUID обновляемого документа
        document_data: Данные для обновления (частичные - только изменяемые поля)
        current_user: Текущий аутентифицированный пользователь
        db: Асинхронная сессия базы данных

    Returns:
        DocumentResponse: Обновлённые данные документа

    Raises:
        DocumentNotFoundError: Если документ не найден или принадлежит другому пользователю
    """
    update_data = document_data.model_dump(exclude_unset=True, by_alias=False)

    if not update_data:
        document = await db.get(DocumentModel, document_id)
        if not document or document.user_id != current_user.id:
            raise DocumentNotFoundError(f"Document {document_id} not found")
        return DocumentResponse.model_validate(document)

    result = await db.execute(
        update(DocumentModel)
        .where(
            DocumentModel.id == document_id,
            DocumentModel.user_id == current_user.id,
            DocumentModel.is_archived.is_(False),
        )
        .values(**update_data)
        .returning(DocumentModel)
    )

    document = result.scalar_one_or_none()

    if not document:
        raise DocumentNotFoundError(f"Document {document_id} not found")

    await db.commit()

    logger.info(f"Документ пользователя успешно обновлён: {document_id}")

    return DocumentResponse.model_validate(document)


async def delete_user_document(document_id: UUID, current_user: UserModel, db: AsyncSession) -> None:
    """
    Удалить документ (мягкое удаление).

    Документ помечается как архивированный (is_archived=True) и исключается
    из основного списка, но остаётся в базе данных. Мягкое удаление позволяет
    восстановить документ при необходимости.

    Args:
        document_id: UUID удаляемого документа
        current_user: Текущий аутентифицированный пользователь
        db: Асинхронная сессия базы данных

    Returns:
        None

    Raises:
        DocumentNotFoundError: Если документ не найден, уже архивирован
            или принадлежит другому пользователю

    Note:
        Функция выполняет мягкое удаление - документ физически остаётся
        в базе данных, но помечается как is_archived=True
    """
    result = await db.scalars(
        select(DocumentModel).where(
            DocumentModel.id == document_id,
            DocumentModel.user_id == current_user.id,
            DocumentModel.is_archived.is_(False),
        )
    )

    document = result.first()

    if not document:
        raise DocumentNotFoundError(f"Document {document_id} not found")

    document.is_archived = True

    await db.commit()

    logger.info(f"Документ {document_id} помечен как архивированный")
