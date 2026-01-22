"""
Тесты для upload endpoints API v2.

Покрывает все основные сценарии:
- Успешный импорт диалогов Claude.ai
- Успешный импорт диалогов GPT
- Валидация расширения файла
- Валидация MIME типа
- Валидация размера файла
- Обработка ошибок
"""

import json
from io import BytesIO

import pytest
from httpx import AsyncClient


# ============================================================
# Фикстуры для тестовых файлов
# ============================================================


@pytest.fixture(scope="function")
def sample_claude_json() -> bytes:
    """
    Создаёт тестовый JSON файл в формате Claude.ai.

    Returns:
        bytes: Содержимое JSON файла в байтах
    """
    # Минимальный валидный JSON в формате Claude.ai
    data = {
        "version": "1.0",
        "chat": [
            {
                "uuid": "test-uuid-1",
                "name": "Test Conversation 1",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
                "messages": [
                    {
                        "uuid": "msg-1",
                        "role": "user",
                        "content": "Hello",
                        "created_at": "2024-01-01T00:00:00Z",
                    },
                    {
                        "uuid": "msg-2",
                        "role": "assistant",
                        "content": "Hi there!",
                        "created_at": "2024-01-01T00:00:00Z",
                    },
                ],
            }
        ],
    }
    return json.dumps(data).encode("utf-8")


@pytest.fixture(scope="function")
def sample_gpt_json() -> bytes:
    """
    Создаёт тестовый JSON файл в формате GPT.

    Returns:
        bytes: Содержимое JSON файла в байтах
    """
    # Минимальный валидный JSON в формате GPT
    data = {
        "conversations": [
            {
                "id": "conv-1",
                "title": "Test Conversation",
                "mapping": {
                    "msg-1": {
                        "role": "user",
                        "content": "Hello",
                    },
                    "msg-2": {
                        "role": "assistant",
                        "content": "Hi there!",
                    },
                },
            }
        ]
    }
    return json.dumps(data).encode("utf-8")


# ============================================================
# POST /upload/conversations_import - импорт диалогов
# ============================================================


@pytest.mark.asyncio
async def test_upload_claude_success(
    client_with_mocked_background: AsyncClient,
    auth_headers: dict[str, str],
    sample_claude_json: bytes,
) -> None:
    """Тест: успешный импорт Claude.ai диалогов"""
    files = {"file": ("claude_conversations.json", BytesIO(sample_claude_json), "application/json")}

    response = await client_with_mocked_background.post(
        "/api/v2/upload/conversations_import?provider=claude",
        headers=auth_headers,
        files=files,
    )

    assert response.status_code == 201

    result = response.json()
    assert result["filename"] == "claude_conversations.json"
    assert result["content_type"] == "application/json"
    assert result["provider"] == "claude"
    assert "size_bytes" in result
    assert "size_mb" in result
    assert result["message"] == "File successfully uploaded"


@pytest.mark.asyncio
async def test_upload_gpt_success(
    client_with_mocked_background: AsyncClient,
    auth_headers: dict[str, str],
    sample_gpt_json: bytes,
) -> None:
    """Тест: успешный импорт GPT диалогов"""
    files = {"file": ("gpt_conversations.json", BytesIO(sample_gpt_json), "application/json")}

    response = await client_with_mocked_background.post(
        "/api/v2/upload/conversations_import?provider=gpt",
        headers=auth_headers,
        files=files,
    )

    assert response.status_code == 201

    result = response.json()
    assert result["filename"] == "gpt_conversations.json"
    assert result["content_type"] == "application/json"
    assert result["provider"] == "gpt"
    assert "size_bytes" in result
    assert "size_mb" in result
    assert result["message"] == "File successfully uploaded"


@pytest.mark.asyncio
async def test_upload_unauthorized(
    client_with_mocked_background: AsyncClient,
    sample_claude_json: bytes,
) -> None:
    """Тест: загрузка без авторизации"""
    files = {"file": ("test.json", BytesIO(sample_claude_json), "application/json")}

    response = await client_with_mocked_background.post(
        "/api/v2/upload/conversations_import?provider=claude",
        files=files,
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_upload_invalid_extension(
    client_with_mocked_background: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Тест: загрузка файла с неверным расширением"""
    files = {"file": ("test.txt", BytesIO(b"some text content"), "text/plain")}

    response = await client_with_mocked_background.post(
        "/api/v2/upload/conversations_import?provider=claude",
        headers=auth_headers,
        files=files,
    )

    assert response.status_code == 400
    assert "Unsupported file extension" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_invalid_mime_type(
    client_with_mocked_background: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Тест: загрузка файла с неверным MIME типом"""
    # JSON данные но с неверным content_type
    files = {"file": ("test.json", BytesIO(b'{"test": "data"}'), "text/plain")}

    response = await client_with_mocked_background.post(
        "/api/v2/upload/conversations_import?provider=claude",
        headers=auth_headers,
        files=files,
    )

    assert response.status_code == 415
    assert "Unsupported file type" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_empty_file(
    client_with_mocked_background: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Тест: загрузка пустого файла"""
    files = {"file": ("empty.json", BytesIO(b""), "application/json")}

    response = await client_with_mocked_background.post(
        "/api/v2/upload/conversations_import?provider=claude",
        headers=auth_headers,
        files=files,
    )

    # Пустой файл должен быть принят (0 байт)
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_upload_invalid_json(
    client_with_mocked_background: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Тест: загрузка невалидного JSON файла"""
    files = {"file": ("invalid.json", BytesIO(b"not a valid json"), "application/json")}

    response = await client_with_mocked_background.post(
        "/api/v2/upload/conversations_import?provider=claude",
        headers=auth_headers,
        files=files,
    )

    # Файл должен быть загружен (валидация только формата файла), но фоновая задача может fail
    # На уровне endpoint - успешная загрузка
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_upload_missing_provider(
    client_with_mocked_background: AsyncClient,
    auth_headers: dict[str, str],
    sample_claude_json: bytes,
) -> None:
    """Тест: загрузка без указания провайдера"""
    files = {"file": ("test.json", BytesIO(sample_claude_json), "application/json")}

    response = await client_with_mocked_background.post(
        "/api/v2/upload/conversations_import",
        headers=auth_headers,
        files=files,
    )

    # Должна быть ошибка валидации (422)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_upload_invalid_provider(
    client_with_mocked_background: AsyncClient,
    auth_headers: dict[str, str],
    sample_claude_json: bytes,
) -> None:
    """Тест: загрузка с неверным провайдером"""
    files = {"file": ("test.json", BytesIO(sample_claude_json), "application/json")}

    response = await client_with_mocked_background.post(
        "/api/v2/upload/conversations_import?provider=unknown_provider",
        headers=auth_headers,
        files=files,
    )

    # Должна быть ошибка валидации enum
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_upload_filename_with_json_extension(
    client_with_mocked_background: AsyncClient,
    auth_headers: dict[str, str],
    sample_claude_json: bytes,
) -> None:
    """Тест: файл с расширением .json (заглавные буквы)"""
    files = {"file": ("TEST.JSON", BytesIO(sample_claude_json), "application/json")}

    response = await client_with_mocked_background.post(
        "/api/v2/upload/conversations_import?provider=claude",
        headers=auth_headers,
        files=files,
    )

    # Должен пройти валидацию (проверка case-insensitive)
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_upload_response_fields(
    client_with_mocked_background: AsyncClient,
    auth_headers: dict[str, str],
    sample_claude_json: bytes,
) -> None:
    """Тест: проверка всех полей в ответе"""
    files = {"file": ("test.json", BytesIO(sample_claude_json), "application/json")}

    response = await client_with_mocked_background.post(
        "/api/v2/upload/conversations_import?provider=claude",
        headers=auth_headers,
        files=files,
    )

    assert response.status_code == 201

    result = response.json()
    # Проверяем все ожидаемые поля
    expected_fields = {
        "filename",
        "content_type",
        "size_bytes",
        "size_mb",
        "message",
        "provider",
    }
    assert set(result.keys()) == expected_fields

    # Проверяем типы данных
    assert isinstance(result["filename"], str)
    assert isinstance(result["content_type"], str)
    assert isinstance(result["size_bytes"], int)
    assert isinstance(result["size_mb"], (int, float))
    assert isinstance(result["message"], str)
    assert isinstance(result["provider"], str)


# ============================================================
# Edge cases
# ============================================================


@pytest.mark.asyncio
async def test_upload_special_characters_in_filename(
    client_with_mocked_background: AsyncClient,
    auth_headers: dict[str, str],
    sample_claude_json: bytes,
) -> None:
    """Тест: файл с спецсимволами в названии"""
    filename = "conversations (1) [test].json"
    files = {"file": (filename, BytesIO(sample_claude_json), "application/json")}

    response = await client_with_mocked_background.post(
        "/api/v2/upload/conversations_import?provider=claude",
        headers=auth_headers,
        files=files,
    )

    assert response.status_code == 201
    assert response.json()["filename"] == filename


@pytest.mark.asyncio
async def test_upload_unicode_filename(
    client_with_mocked_background: AsyncClient,
    auth_headers: dict[str, str],
    sample_claude_json: bytes,
) -> None:
    """Тест: файл с Unicode в названии"""
    filename = "диалоги.json"
    files = {"file": (filename, BytesIO(sample_claude_json), "application/json")}

    response = await client_with_mocked_background.post(
        "/api/v2/upload/conversations_import?provider=claude",
        headers=auth_headers,
        files=files,
    )

    assert response.status_code == 201
