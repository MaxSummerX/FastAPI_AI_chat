"""
Тесты глобальных exception handlers (presentation/exceptions.py).

Покрывают новую логику, которой нет в существующих тестах роутеров:
- маппинг доменных исключений в HTTP-статусы по STATUS_MAP
- поиск по MRO для наследников (LLMGenerationError → LLMError → 503)
- заголовок WWW-Authenticate: Bearer на 401
- отдельный хендлер InvalidCursorError → 400
- новая семантика ошибок hh.ru (fetch → 502, а не маскировка 404)
- безопасный 500 для незамапленных исключений (без утечки текста)
"""

from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.exceptions.base import BaseAppException
from app.application.exceptions.fact import FactNotFoundException
from app.application.exceptions.llm import LLMGenerationError
from app.presentation.dependencies import get_fact_service, get_message_service, get_vacancy_service
from app.presentation.exceptions import STATUS_MAP


class _RaisingService:
    """Заглушка сервиса: любой метод бросает заданное исключение."""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def __getattr__(self, name: str) -> Any:
        async def _raise(*args: Any, **kwargs: Any) -> Any:
            raise self._exc

        return _raise


class _UnmappedDummyError(BaseAppException):
    """Доменное исключение, специально не внесённое в STATUS_MAP."""

    pass


@pytest.fixture
async def raising_client(client: AsyncClient, db_session: AsyncSession) -> AsyncGenerator[tuple[AsyncClient, FastAPI]]:
    """Клиент с подменёнными сервисами на бросающие заглушки.

    Исключение задаётся через сервис-поле raise_exc внутри теста
    (объект общий, тип исключения подменяется перед запросом).
    """
    from app.main import app

    holder = _RaisingService(FactNotFoundException("Факт не найден"))

    app.dependency_overrides[get_fact_service] = lambda: holder
    app.dependency_overrides[get_message_service] = lambda: holder
    app.dependency_overrides[get_vacancy_service] = lambda: holder

    try:
        yield client, app
    finally:
        app.dependency_overrides.pop(get_fact_service, None)
        app.dependency_overrides.pop(get_message_service, None)
        app.dependency_overrides.pop(get_vacancy_service, None)


@pytest.mark.asyncio
async def test_not_found_maps_404(raising_client: tuple[AsyncClient, FastAPI], auth_headers: dict[str, str]) -> None:
    """FactNotFoundException из сервиса → 404, detail = текст исключения."""
    client, _ = raising_client
    response = await client.get(f"/api/v1/facts/{uuid4()}", headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Факт не найден"


@pytest.mark.asyncio
async def test_llm_error_maps_503_via_mro(
    raising_client: tuple[AsyncClient, FastAPI], auth_headers: dict[str, str]
) -> None:
    """LLMGenerationError сам не в STATUS_MAP — статус находится по MRO через LLMError → 503."""
    assert LLMGenerationError not in STATUS_MAP  # предусловие теста

    client, app = raising_client
    # Подменяем исключение заглушки на LLM-ошибку
    app.dependency_overrides[get_message_service]()._exc = LLMGenerationError(  # noqa: SLF001
        "Не удалось получить ответ от LLM"
    )
    response = await client.post(
        f"/api/v1/conversations/{uuid4()}/messages/stream",
        headers=auth_headers,
        json={
            "message": {"role": "user", "content": "привет"},
            "mem0ai_on": False,
            "mem0ai_save": False,
        },
    )
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_401_has_www_authenticate_header(client: AsyncClient) -> None:
    """401 от доменного исключения несёт заголовок WWW-Authenticate: Bearer.

    Логин с неверным паролем: AuthService бросает InvalidCredentialsException,
    глобальный хендлер маппит в 401 и добавляет заголовок.
    """
    response = await client.post("/api/v1/user/token", data={"username": "nobody", "password": "wrong"})
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


@pytest.mark.asyncio
async def test_invalid_cursor_maps_400(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    """InvalidCursorError (не BaseAppException) → 400 от отдельного хендлера."""
    response = await client.get("/api/v1/facts", headers=auth_headers, params={"cursor": "invalid_cursor_base64"})
    assert response.status_code == 400
    assert "cursor" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_fetch_error_maps_502_not_404(
    raising_client: tuple[AsyncClient, FastAPI], auth_headers: dict[str, str]
) -> None:
    """VacancyFetchError при импорте hh-вакансии → 502 (раньше маскировался под 404)."""
    from app.application.exceptions.vacancy import VacancyFetchError

    client, app = raising_client
    # Подменяем исключение заглушки на ошибку загрузки с hh.ru
    app.dependency_overrides[get_vacancy_service]()._exc = VacancyFetchError(  # noqa: SLF001
        "Не удалось загрузить вакансию 12345678"
    )
    response = await client.post("/api/v1/vacancies/head_hunter/12345678", headers=auth_headers)
    assert response.status_code == 502


@pytest.mark.asyncio
async def test_unmapped_exception_safe_500(
    raising_client: tuple[AsyncClient, FastAPI], auth_headers: dict[str, str]
) -> None:
    """Незамапленное доменное исключение → 500 без внутренних деталей."""
    client, app = raising_client
    holder = app.dependency_overrides[get_fact_service]()
    holder._exc = _UnmappedDummyError("внутренняя диагностика с секретами")  # noqa: SLF001

    assert _UnmappedDummyError not in STATUS_MAP  # предусловие теста

    response = await client.get(f"/api/v1/facts/{uuid4()}", headers=auth_headers)
    assert response.status_code == 500
    # Наружу уходит только безопасный текст, без текста исключения
    assert response.json()["detail"] == "Internal server error"
    assert "секреты" not in response.text
