"""
Парсер веб-страниц hh.ru через HH-Lux-InitialState.

Функции модуля возвращают словари в форме старого API hh.ru чтобы потребители не менялись.
"""

import asyncio
import html
import json
import random
from typing import Any

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from app.infrastructure.hh.exceptions import RateLimitError


SEARCH_PATH = "/search/vacancy"
VACANCY_PATH = "/vacancy/{vacancy_id}"

PER_PAGE = 100  # максимум hh.ru на страницу поиска

# Параметры человекоподобных пауз (см. polite_sleep)
SLEEP_MIN = 1.0  # нижняя граница паузы (сек)
SLEEP_MAX = 8.0  # обрезка хвоста lognormal (сек), чтобы не убивать throughput
DISTRACTION_CHANCE = 0.08  # вероятность "отвлечения"
DISTRACTION_RANGE = (4.0, 12.0)  # длительность "отвлечения" (сек)

_rng = random.Random()  # nosec B311


class HHAntiBotError(Exception):
    """Страница недоступна: капча/блок (нет Lux-InitialState, статус 403)."""


def _search_params(query: str, page: int) -> dict[str, Any]:
    """
    Query-параметры для /search/vacancy — копия параметров веб-поиска hh.ru.

    Переменные части (текст запроса, номер страницы) — в аргументах,
    остальное — фиксированная политика поиска (см. комментарии в словаре).
    """
    return {
        "text": query,
        "page": page,
        "items_on_page": PER_PAGE,
        "ored_clusters": "true",
        # поиск по названию/компании/описанию + сниппеты (snippet.req / snippet.resp)
        "search_field": ["name", "company_name", "description"],
        "enable_snippets": "true",
    }


def _unescape_values(node: Any) -> Any:
    """
    Рекурсивно применяет html.unescape к строковым значениям распаренного JSON.

    ВАЖНО: unescape нельзя делать ДО json.loads — сущности вида &quot;
    превратятся в кавычки и сломают синтаксис JSON.
    """
    if isinstance(node, str):
        return html.unescape(node)
    if isinstance(node, list):
        return [_unescape_values(item) for item in node]
    if isinstance(node, dict):
        return {key: _unescape_values(value) for key, value in node.items()}
    return node


async def _get_lux_state(
    client: httpx.AsyncClient,
    path: str,
    params: dict[str, Any],
    max_attempts: int = 3,
) -> dict[str, Any]:
    """
    Запрашивает страницу hh.ru и достаёт JSON из HH-Lux-InitialState.

    Временные сетевые сбои (обрыв keepalive, timeout) retry с backoff.

    Raises:
        RateLimitError: 429
        HHAntiBotError: 403 или Lux-InitialState отсутствует (капча/блок)
        httpx.HTTPError: прочие сетевые/HTTP ошибки
    """
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = await client.get(path, params=params)
            break
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as e:
            # hh.ru периодически обрывает keepalive-соединения — это не блок
            last_error = e
            if attempt == max_attempts:
                raise
            wait = 2**attempt
            logger.warning(f"Сетевой сбой при запросе {path} (попытка {attempt}/{max_attempts}): {e}, ждём {wait}с")
            await asyncio.sleep(wait)
    else:  # pragma: no cover
        raise last_error  # type: ignore[misc]

    if response.status_code == 429:
        raise RateLimitError(f"429 от hh.ru: {path}")
    if response.status_code == 403:
        raise HHAntiBotError(f"403 от hh.ru (возможен блок): {path}")
    response.raise_for_status()

    template = BeautifulSoup(response.text, "lxml").find("template", id="HH-Lux-InitialState")
    content = template.string if template is not None else None
    if content is None:
        raise HHAntiBotError(f"HH-Lux-InitialState не найден: {path}")

    # Сначала парсим JSON "как есть", затем разэкранируем HTML-сущности
    # в значениях (внутри description встречаются &quot; и т.п.)
    state: dict[str, Any] = _unescape_values(json.loads(content))
    return state


# =============================================================================
# Маппинг Lux -> форма старого API hh.ru
# =============================================================================


def _compensation_to_salary(lux: dict[str, Any]) -> dict[str, Any] | None:
    comp = lux.get("compensation")
    if not isinstance(comp, dict):
        return None
    return {
        "from": comp.get("from"),
        "to": comp.get("to"),
        "currency": comp.get("currencyCode"),
        "gross": comp.get("gross"),
    }


def _publication_time(lux: dict[str, Any]) -> str | None:
    # список: publicationTime={"@timestamp": ..., "$": "ISO"}; детали: publicationDate="ISO"
    pub = lux.get("publicationTime")
    if isinstance(pub, dict):
        return pub.get("$")
    return lux.get("publicationDate")


def _map_common(lux: dict[str, Any]) -> dict[str, Any]:
    """Общие поля карточки вакансии (список и страница деталей)."""
    area = lux.get("area") or {}
    company = lux.get("company") or {}
    links = lux.get("links") or {}
    employment_form = lux.get("employmentForm")

    return {
        "id": str(lux.get("vacancyId")) if lux.get("vacancyId") is not None else None,
        "name": lux.get("name"),
        "salary": _compensation_to_salary(lux),
        "experience": {"id": lux["workExperience"]} if lux.get("workExperience") else None,
        "employment": {"id": employment_form.lower()} if employment_form else None,
        # id региона/работодателя приводим к str — в БД колонки VARCHAR,
        # а Lux отдаёт числа (старое API hh возвращало строки)
        "area": {"id": str(area["@id"]) if area.get("@id") is not None else None, "name": area.get("name")}
        if area
        else None,
        "employer": {
            "id": str(company["id"]) if company.get("id") is not None else None,
            "name": company.get("visibleName"),
        }
        if company
        else None,
        # schedule в приложении не используется, честного аналога в Lux нет
        "schedule": None,
        "alternate_url": links.get("desktop"),
        "published_at": _publication_time(lux),
    }


def lux_item_to_api(item: dict[str, Any]) -> dict[str, Any]:
    """Карточка из результатов поиска -> форма элемента items старого API."""
    return _map_common(item)


def vacancy_view_to_api(vacancy_view: dict[str, Any]) -> dict[str, Any]:
    """
    vacationView со страницы вакансии -> форма ответа /vacancies/{id} старого API.
    Добавляет description и archived, которых нет в списке.
    """
    result = _map_common(vacancy_view)
    result.update(
        {
            "description": vacancy_view.get("description"),
            "archived": bool((vacancy_view.get("status") or {}).get("archived", False)),
            "key_skills": list((vacancy_view.get("keySkills") or {}).get("keySkill", [])),
            # на странице деталей links нет — собираем сами
            "alternate_url": result.get("alternate_url") or f"https://hh.ru/vacancy/{vacancy_view.get('vacancyId')}",
        }
    )
    return result


# =============================================================================
# Публичные функции
# =============================================================================


async def fetch_search_page(
    client: httpx.AsyncClient,
    query: str,
    page: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """
    Одна страница поиска hh.ru.

    Returns:
        (вакансии в форме старого API без рекламы, totalResults по запросу)
    """
    lux = await _get_lux_state(client, SEARCH_PATH, _search_params(query, page))
    search_result = lux.get("vacancySearchResult", {})

    items = [
        lux_item_to_api(item)
        for item in search_result.get("vacancies", [])
        if not item.get("@isAdv")  # рекламные вставки фильтруем
    ]
    total = int(search_result.get("totalResults", 0))
    return items, total


async def fetch_vacancy_details(client: httpx.AsyncClient, hh_id: str) -> dict[str, Any] | None:
    """
    Полные детали вакансии со страницы hh.ru/vacancy/{id}.

    Returns:
        Словарь в форме старого API или None, если вакансия не найдена (404).
    """
    path = VACANCY_PATH.format(vacancy_id=hh_id)
    try:
        lux = await _get_lux_state(client, path, {})
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        raise
    vacancy_view = lux.get("vacancyView")
    if not isinstance(vacancy_view, dict):
        logger.warning("vacancyView отсутствует на странице вакансии {}", hh_id)
        return None
    return vacancy_view_to_api(vacancy_view)


async def polite_sleep(delay: float = 0.0) -> None:
    """
    Человекоподобная пауза между запросами к hh.ru.

    Форма распределения важнее среднего: анти-бот строит гистограмму
    интервалов за сессию и сравнивает с типовым поведением живого
    пользователя. Ровные (uniform/константные) интервалы — самый громкий
    сигнал автоматики, поэтому:

    - база берётся из lognormal: много коротких пауз (пользователь быстро
      листает выдачу) с тяжёлым правым хвостом (залип на вакансии);
    - хвост обрезан сверху, чтобы редкая пауза не убивала throughput;
    - с шансом DISTRACTION_CHANCE вставляется "отвлечение" — длинная пауза,
      как будто пользователь ушёл читать/отвлёкся: человек НИКОГДА не листает
      сотни страниц с одинаковым ритмом, отсутствие таких пауз — само по
      себе маркер бота;
    - мелкий шум поверх, чтобы две одинаковые базы не дали идентичное время.
    """
    if delay > 0:
        base = delay
    else:
        # lognormal(mu=0.5, sigma=0.7): мода ~1с, медиана ~1.6с, хвост до ~8с
        base = _rng.lognormvariate(0.5, 0.7)
        base = max(base, SLEEP_MIN)
        base = min(base, SLEEP_MAX)
        if _rng.random() < DISTRACTION_CHANCE:
            base += _rng.uniform(*DISTRACTION_RANGE)
    await asyncio.sleep(base + _rng.uniform(0, 0.3))


def pages_for_total(total: int, max_pages: int) -> int:
    """Сколько страниц поиска нужно пройти (ceil, с ограничением сверху)."""
    return min(-(-total // PER_PAGE), max_pages)
