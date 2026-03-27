"""
Тесты для document endpoints API v2.

Покрывает все основные сценарии:
- Получение документов с курсорной пагинацией
- Фильтрация по категории
- Создание, обновление, удаление документов
- Обработка ошибок и авторизации
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums.document import DocumentCategory
from app.domain.models.document import Document as DocumentModel


# ============================================================
# GET /documents - курсорная пагинация
# ============================================================


@pytest.mark.asyncio
async def test_get_documents_unauthorized(client: AsyncClient) -> None:
    """Тест: неавторизованный запрос к documents"""
    response = await client.get("/api/v2/documents")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_documents_empty(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: получение документов когда их нет"""
    response = await client.get("/api/v2/documents", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert "items" in data
    assert "next_cursor" in data
    assert "has_next" in data
    assert len(data["items"]) == 0
    assert data["has_next"] is False
    assert data["next_cursor"] is None


@pytest.mark.asyncio
async def test_get_documents_first_page(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_documents: list[DocumentModel],
) -> None:
    """Тест: первая страница документов (без cursor)"""
    response = await client.get("/api/v2/documents", headers=auth_headers, params={"limit": 15})
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) == 15
    assert data["has_next"] is True
    assert data["next_cursor"] is not None


@pytest.mark.asyncio
async def test_get_documents_with_cursor(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_documents: list[DocumentModel],
) -> None:
    """Тест: вторая страница документов (с cursor)"""
    # Первая страница
    first_response = await client.get("/api/v2/documents", headers=auth_headers, params={"limit": 10})
    first_data = first_response.json()
    cursor = first_data["next_cursor"]

    # Вторая страница
    response = await client.get(
        "/api/v2/documents",
        headers=auth_headers,
        params={"limit": 10, "cursor": cursor},
    )
    assert response.status_code == 200

    data = response.json()
    assert len(data["items"]) == 10
    assert data["has_next"] is True


@pytest.mark.asyncio
async def test_get_documents_pagination_to_end(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_documents: list[DocumentModel],
) -> None:
    """Тест: пагинация до конца (все документы загружены)"""
    all_items = []
    cursor = None

    for _ in range(10):
        params = {"limit": 10}
        if cursor:
            params["cursor"] = cursor

        response = await client.get("/api/v2/documents", headers=auth_headers, params=params)
        data = response.json()

        all_items.extend(data["items"])

        if not data["has_next"]:
            break

        cursor = data["next_cursor"]

    # Должны загрузить все 30 документов
    assert len(all_items) == 30


@pytest.mark.asyncio
async def test_get_documents_invalid_cursor(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: использование невалидного курсора"""
    response = await client.get(
        "/api/v2/documents",
        headers=auth_headers,
        params={"cursor": "invalid_cursor_base64"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_documents_ordering_desc(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_documents: list[DocumentModel],
) -> None:
    """Тест: проверка правильности сортировки (от нового к старому)"""
    response = await client.get("/api/v2/documents", headers=auth_headers, params={"limit": 10})
    assert response.status_code == 200

    data = response.json()
    items = data["items"]

    # Проверяем сортировку от НОВОГО к СТАРОМУ (DESC)
    for i in range(len(items) - 1):
        current_timestamp = items[i]["created_at"]
        next_timestamp = items[i + 1]["created_at"]
        assert current_timestamp >= next_timestamp


@pytest.mark.asyncio
async def test_get_documents_filter_by_category(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_documents: list[DocumentModel],
) -> None:
    """Тест: фильтрация документов по категории"""
    response = await client.get(
        "/api/v2/documents",
        headers=auth_headers,
        params={"category": "note", "limit": 100},
    )
    assert response.status_code == 200

    data = response.json()
    # Все документы должны быть категории note
    for document in data["items"]:
        assert document["category"] == "note"


@pytest.mark.asyncio
async def test_get_documents_include_archived(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session: AsyncSession,
    test_documents: list[DocumentModel],
) -> None:
    """Тест: включение архивированных документов"""
    # Архивируем первый документ
    test_documents[0].is_archived = True
    await db_session.commit()

    # Без include_archived - архивированные не возвращаются
    response_active = await client.get("/api/v2/documents", headers=auth_headers, params={"limit": 100})
    active_data = response_active.json()
    assert len(active_data["items"]) == 29

    # С include_archived - все документы
    response_all = await client.get(
        "/api/v2/documents",
        headers=auth_headers,
        params={"include_archived": True, "limit": 100},
    )
    all_data = response_all.json()
    assert len(all_data["items"]) == 30


@pytest.mark.asyncio
async def test_get_documents_limit_validation(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: валидация limit параметра"""
    # Слишком большой limit - использует максимум
    response = await client.get("/api/v2/documents", headers=auth_headers, params={"limit": 150})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_documents_limit_minimum(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: limit меньше минимума возвращает ошибку валидации"""
    response = await client.get("/api/v2/documents", headers=auth_headers, params={"limit": 0})
    assert response.status_code == 422


# ============================================================
# GET /documents/{document_id} - получение документа по ID
# ============================================================


@pytest.mark.asyncio
async def test_get_document_unauthorized(client: AsyncClient, test_document: DocumentModel) -> None:
    """Тест: получение документа без авторизации"""
    response = await client.get(f"/api/v2/documents/{test_document.id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_document_success(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_document: DocumentModel,
) -> None:
    """Тест: успешное получение документа"""
    response = await client.get(f"/api/v2/documents/{test_document.id}", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == str(test_document.id)
    assert data["content"] == test_document.content
    assert data["category"] == test_document.category


@pytest.mark.asyncio
async def test_get_document_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: получение несуществующего документа"""
    response = await client.get(f"/api/v2/documents/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_document_archived(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_document: DocumentModel,
    db_session: AsyncSession,
) -> None:
    """Тест: получение архивированного документа"""
    test_document.is_archived = True
    await db_session.commit()

    response = await client.get(f"/api/v2/documents/{test_document.id}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_document_other_user(
    client: AsyncClient,
    admin_headers: dict[str, str],
    test_document: DocumentModel,
) -> None:
    """Тест: попытка получить документ другого пользователя"""
    response = await client.get(f"/api/v2/documents/{test_document.id}", headers=admin_headers)
    assert response.status_code == 404


# ============================================================
# POST /documents - создание документа
# ============================================================


@pytest.mark.asyncio
async def test_create_document_unauthorized(client: AsyncClient) -> None:
    """Тест: создание документа без авторизации"""
    response = await client.post(
        "/api/v2/documents",
        json={
            "content": "Test document content",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_document_success(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: успешное создание документа"""
    response = await client.post(
        "/api/v2/documents",
        headers=auth_headers,
        json={
            "title": "Test Document",
            "content": "This is a test document content",
            "category": "note",
        },
    )
    assert response.status_code == 202

    data = response.json()
    assert data["title"] == "Test Document"
    assert data["content"] == "This is a test document content"
    assert data["category"] == "note"
    assert "id" in data
    assert data["is_archived"] is False


@pytest.mark.asyncio
async def test_create_document_with_tags(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: создание документа с тегами"""
    response = await client.post(
        "/api/v2/documents",
        headers=auth_headers,
        json={
            "title": "Document with Tags",
            "content": "Content here",
            "tags": ["python", "fastapi", "testing"],
        },
    )
    assert response.status_code == 202

    data = response.json()
    assert data["tags"] == ["python", "fastapi", "testing"]


@pytest.mark.asyncio
async def test_create_document_with_metadata(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: создание документа с метаданными"""
    metadata = {"source": "manual", "priority": "high", "author": "test_user"}

    response = await client.post(
        "/api/v2/documents",
        headers=auth_headers,
        json={
            "title": "Document with Metadata",
            "content": "Content",
            "metadata_": metadata,
        },
    )
    assert response.status_code == 202

    data = response.json()
    assert data["metadata_"] == metadata


@pytest.mark.asyncio
async def test_create_document_default_category(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: создание документа с категорией по умолчанию (note)"""
    response = await client.post(
        "/api/v2/documents",
        headers=auth_headers,
        json={
            "content": "Minimal document",
        },
    )
    assert response.status_code == 202

    data = response.json()
    assert data["category"] == DocumentCategory.NOTE


@pytest.mark.asyncio
async def test_create_document_empty_content(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: создание документа с пустым контентом"""
    response = await client.post(
        "/api/v2/documents",
        headers=auth_headers,
        json={
            "content": "   ",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_document_content_too_short(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: контент короче минимума (5 символов)"""
    response = await client.post(
        "/api/v2/documents",
        headers=auth_headers,
        json={
            "content": "abc",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_document_title_too_long(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: заголовок длиннее максимума (255 символов)"""
    response = await client.post(
        "/api/v2/documents",
        headers=auth_headers,
        json={
            "title": "x" * 256,
            "content": "Valid content",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_document_all_categories(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: создание документов всех категорий"""
    for category in DocumentCategory:
        response = await client.post(
            "/api/v2/documents",
            headers=auth_headers,
            json={
                "title": f"Document {category}",
                "content": f"Content for {category}",
                "category": category,
            },
        )
        assert response.status_code == 202

        data = response.json()
        assert data["category"] == category


# ============================================================
# PATCH /documents/{document_id} - обновление документа
# ============================================================


@pytest.mark.asyncio
async def test_update_document_unauthorized(client: AsyncClient, test_document: DocumentModel) -> None:
    """Тест: обновление документа без авторизации"""
    response = await client.patch(
        f"/api/v2/documents/{test_document.id}",
        json={"title": "Updated Title"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_document_success(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_document: DocumentModel,
) -> None:
    """Тест: успешное обновление документа"""
    response = await client.patch(
        f"/api/v2/documents/{test_document.id}",
        headers=auth_headers,
        json={
            "title": "Updated Title",
            "content": "Updated content",
        },
    )
    assert response.status_code == 202

    data = response.json()
    assert data["id"] == str(test_document.id)
    assert data["title"] == "Updated Title"
    assert data["content"] == "Updated content"


@pytest.mark.asyncio
async def test_update_document_partial(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_document: DocumentModel,
) -> None:
    """Тест: частичное обновление документа (только заголовок)"""
    original_content = test_document.content

    response = await client.patch(
        f"/api/v2/documents/{test_document.id}",
        headers=auth_headers,
        json={
            "title": "New Title Only",
        },
    )
    assert response.status_code == 202

    data = response.json()
    assert data["title"] == "New Title Only"
    assert data["content"] == original_content  # Контент не изменился


@pytest.mark.asyncio
async def test_update_document_category(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_document: DocumentModel,
) -> None:
    """Тест: обновление категории документа"""
    response = await client.patch(
        f"/api/v2/documents/{test_document.id}",
        headers=auth_headers,
        json={
            "category": "code",
        },
    )
    assert response.status_code == 202

    data = response.json()
    assert data["category"] == "code"


@pytest.mark.asyncio
async def test_update_document_tags(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_document: DocumentModel,
) -> None:
    """Тест: обновление тегов документа"""
    response = await client.patch(
        f"/api/v2/documents/{test_document.id}",
        headers=auth_headers,
        json={
            "tags": ["new-tag", "another-tag"],
        },
    )
    assert response.status_code == 202

    data = response.json()
    assert data["tags"] == ["new-tag", "another-tag"]


@pytest.mark.asyncio
async def test_update_document_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: обновление несуществующего документа"""
    response = await client.patch(
        f"/api/v2/documents/{uuid.uuid4()}",
        headers=auth_headers,
        json={"title": "Updated"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_document_archived(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_document: DocumentModel,
    db_session: AsyncSession,
) -> None:
    """Тест: обновление архивированного документа"""
    test_document.is_archived = True
    await db_session.commit()

    response = await client.patch(
        f"/api/v2/documents/{test_document.id}",
        headers=auth_headers,
        json={"title": "Try to update archived"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_document_other_user(
    client: AsyncClient,
    admin_headers: dict[str, str],
    test_document: DocumentModel,
) -> None:
    """Тест: попытка обновить документ другого пользователя"""
    response = await client.patch(
        f"/api/v2/documents/{test_document.id}",
        headers=admin_headers,
        json={"title": "Hacked!"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_document_empty_body(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_document: DocumentModel,
) -> None:
    """Тест: обновление с пустым телом запроса (возвращает текущий документ)"""
    response = await client.patch(
        f"/api/v2/documents/{test_document.id}",
        headers=auth_headers,
        json={},
    )
    assert response.status_code == 202

    data = response.json()
    assert data["id"] == str(test_document.id)


# ============================================================
# DELETE /documents/{document_id} - удаление документа
# ============================================================


@pytest.mark.asyncio
async def test_delete_document_unauthorized(client: AsyncClient, test_document: DocumentModel) -> None:
    """Тест: удаление документа без авторизации"""
    response = await client.delete(f"/api/v2/documents/{test_document.id}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delete_document_success(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_document: DocumentModel,
    db_session: AsyncSession,
) -> None:
    """Тест: успешное удаление документа (мягкое)"""
    response = await client.delete(f"/api/v2/documents/{test_document.id}", headers=auth_headers)
    assert response.status_code == 204

    # Проверяем что документ помечен как архивированный
    await db_session.refresh(test_document)
    assert test_document.is_archived is True


@pytest.mark.asyncio
async def test_delete_document_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """Тест: удаление несуществующего документа"""
    response = await client.delete(f"/api/v2/documents/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_document_already_archived(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_document: DocumentModel,
    db_session: AsyncSession,
) -> None:
    """Тест: удаление уже архивированного документа"""
    test_document.is_archived = True
    await db_session.commit()

    response = await client.delete(f"/api/v2/documents/{test_document.id}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_document_other_user(
    client: AsyncClient,
    admin_headers: dict[str, str],
    test_document: DocumentModel,
) -> None:
    """Тест: попытка удалить документ другого пользователя"""
    response = await client.delete(f"/api/v2/documents/{test_document.id}", headers=admin_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_then_get_not_found(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_document: DocumentModel,
) -> None:
    """Тест: после удаления документ не находится через GET"""
    # Удаляем документ
    await client.delete(f"/api/v2/documents/{test_document.id}", headers=auth_headers)

    # Пытаемся получить удалённый документ
    response = await client.get(f"/api/v2/documents/{test_document.id}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_then_get_with_include_archived(
    client: AsyncClient,
    auth_headers: dict[str, str],
    test_document: DocumentModel,
    db_session: AsyncSession,
) -> None:
    """Тест: удалённый документ не возвращается в списке без include_archived"""
    # Удаляем документ
    await client.delete(f"/api/v2/documents/{test_document.id}", headers=auth_headers)

    # Без include_archived - документ не возвращается
    response = await client.get("/api/v2/documents", headers=auth_headers, params={"limit": 100})
    data = response.json()
    document_ids = [doc["id"] for doc in data["items"]]
    assert str(test_document.id) not in document_ids

    # С include_archived - документ возвращается
    response_all = await client.get(
        "/api/v2/documents",
        headers=auth_headers,
        params={"include_archived": True, "limit": 100},
    )
    data_all = response_all.json()
    document_ids_all = [doc["id"] for doc in data_all["items"]]
    assert str(test_document.id) in document_ids_all
