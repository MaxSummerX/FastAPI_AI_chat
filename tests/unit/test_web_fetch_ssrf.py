"""Тесты SSRF-защиты web_fetch: блокировка внутренних адресов."""

import json
import socket
from unittest.mock import MagicMock, patch

import pytest

from app.infrastructure.llms.tools import web_fetch


def _error(data: str) -> str:
    """Вытащить текст ошибки из JSON-ответа web_fetch."""
    return str(json.loads(data).get("error", ""))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000/admin",
        "http://127.0.0.1:5432",
        "http://192.168.3.10:6333",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/",
        "http://[::1]:8080/",
    ],
)
async def test_block_internal_hosts(url: str) -> None:
    """Литеральные внутренние адреса — отказ без сетевого запроса."""
    result = await web_fetch(url)
    assert "error" in json.loads(result)


@pytest.mark.asyncio
async def test_blocks_domain_resolving_to_private_ip() -> None:
    """Домен с A-записью на 192.168.x.x — блокируется после резолва."""
    fake_addrinfo = [(socket.AF_INET, None, None, "", ("192.168.1.50", 0))]
    with patch("app.infrastructure.llms.tools.socket.getaddrinfo", return_value=fake_addrinfo):
        result = await web_fetch("http://internal.example/")
    assert "internal address" in _error(result)


@pytest.mark.asyncio
async def test_allows_domain_resolving_to_public_ip() -> None:
    """Домен с публичной A-записью проходит резолв-проверку."""
    fake_addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    fake_response = MagicMock()
    fake_response.headers = {"content-type": "text/markdown"}
    fake_response.text = "# Публичная страница"
    fake_response.status_code = 200
    fake_response.url = "https://example.com/"

    with (
        patch("app.infrastructure.llms.tools.socket.getaddrinfo", return_value=fake_addrinfo),
        patch("app.infrastructure.llms.tools.httpx.AsyncClient") as mock_client,
    ):
        mock_client.return_value.__aenter__.return_value.get.return_value = fake_response

        result = await web_fetch("https://example.com/")

    data = json.loads(result)
    assert "error" not in data
    assert data["status"] == 200


@pytest.mark.asyncio
async def test_allows_public_url() -> None:
    """Публичный домен проходит проверку (дальше — реальный запрос)."""
    fake_addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
    fake_response = MagicMock()
    fake_response.headers = {"content-type": "text/markdown"}
    fake_response.text = "# Заголовок страницы"
    fake_response.status_code = 200
    fake_response.url = "https://example.com/page"

    with (
        patch("app.infrastructure.llms.tools.socket.getaddrinfo", return_value=fake_addrinfo),
        patch("app.infrastructure.llms.tools.httpx.AsyncClient") as mock_client,
    ):
        mock_client.return_value.__aenter__.return_value.get.return_value = fake_response

        result = await web_fetch("https://example.com/page")

    data = json.loads(result)
    assert "error" not in data
    assert data["status"] == 200
    assert data["text"] == "# Заголовок страницы"
    mock_client.return_value.__aenter__.return_value.get.assert_awaited_once()
