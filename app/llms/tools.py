import asyncio
import html
import json
import re
from collections.abc import Awaitable, Callable
from urllib.parse import urlparse
from uuid import UUID

import httpx
from ddgs import DDGS
from loguru import logger
from readability import Document


# Общие константы
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36"
MAX_REDIRECTS = 5


def _validate_url(url: str) -> tuple[bool, str]:
    """Проверить URL: должен быть http(s) имея валидный домен."""
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False, f"Only http/https allowed, got '{p.scheme or 'none'}'"
        if not p.netloc:
            return False, "Missing domain"
        return True, ""
    except Exception as e:
        return False, str(e)


def _strip_tags(text: str) -> str:
    """Удалить HTML-теги и декодировать entities."""

    text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _normalize(text: str) -> str:
    """Нормализовать пробелы."""

    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _to_markdown(html_code: str) -> str:
    """Конвертировать HTML в markdown."""

    # Конвертировать ссылки, заголовки, перечни перед удалением тегов
    text = re.sub(
        r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
        lambda m: f"[{_strip_tags(m[2])}]({m[1]})",
        html_code,
        flags=re.I,
    )
    text = re.sub(
        r"<h([1-6])[^>]*>([\s\S]*?)</h\1>",
        lambda m: f"\n{'#' * int(m[1])} {_strip_tags(m[2])}\n",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"<li[^>]*>([\s\S]*?)</li>",
        lambda m: f"\n- {_strip_tags(m[1])}",
        text,
        flags=re.I,
    )
    text = re.sub(r"</(p|div|section|article)>", "\n\n", text, flags=re.I)
    text = re.sub(r"<(br|hr)\s*/?>", "\n", text, flags=re.I)
    return _normalize(_strip_tags(text))


async def web_search(query: str, max_results: int = 5) -> str | None:
    """Поиск через DuckDuckGo (бесплатно, без ключа)."""
    try:
        # Запускаем синхронный DDGS в потоке, не блокируя event loop
        results: list[dict] = await asyncio.to_thread(
            lambda: DDGS().text(query, max_results=min(max(max_results, 1), 10))
        )

        if not results:
            return f"No results for: {query}"

        lines = [f"Results for: {query}\n"]
        for i, item in enumerate(results, 1):
            lines.append(f"{i}. {item.get('title', '')}\n   {item.get('href', '')}")
            if body := item.get("body"):
                lines.append(f"   {body}")

        return "\n".join(lines)

    except Exception as e:
        logger.warning("DDGS search failed: {}", e)
        return None


async def web_fetch(
    url: str, extract_mode: str = "markdown", max_chars: int = 50000, accept_markdown: bool = True
) -> str:
    """Извлечь через Readability (fallback)."""
    try:
        headers = {"User-Agent": USER_AGENT}
        if accept_markdown:
            headers["Accept"] = "text/markdown, text/html, */*"

        async with httpx.AsyncClient(follow_redirects=True, max_redirects=MAX_REDIRECTS, timeout=30.0) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()

        ctype = r.headers.get("content-type", "")

        # Новые заголовки для агента
        markdown_tokens = r.headers.get("x-markdown-tokens")
        content_signal = r.headers.get("content-signal")

        # JSON
        if "application/json" in ctype:
            text, extractor = (
                json.dumps(r.json(), indent=2, ensure_ascii=False),
                "json",
            )
        # Markdown
        elif "text/markdown" in ctype:
            text, extractor = r.text, "markdown"
        # HTML
        elif "text/html" in ctype or r.text[:256].lower().startswith(("<!doctype", "<html")):
            doc = Document(r.text)
            content = _to_markdown(doc.summary()) if extract_mode == "markdown" else _strip_tags(doc.summary())
            text = f"# {doc.title()}\n\n{content}" if doc.title() else content
            extractor = "readability"
        else:
            text, extractor = r.text, "raw"

        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars]

        result = {
            "url": url,
            "finalUrl": str(r.url),
            "status": r.status_code,
            "extractor": extractor,
            "truncated": truncated,
            "length": len(text),
            "text": text,
        }

        # Добавляем markdown-метаданные, если есть
        if markdown_tokens:
            result["markdown_tokens"] = markdown_tokens
        if content_signal:
            result["content_signal"] = content_signal
        return json.dumps(result)

    except Exception as e:
        return json.dumps({"error": str(e), "url": url}, ensure_ascii=False)


def make_create_file_tool(user_id: str | UUID) -> Callable[..., Awaitable[str]]:
    """Создаёт функцию create_file с захваченным user_id.
    db передаётся только для совместимости, но не используется напрямую."""
    from app.infrastructure.database.dependencies import async_session_maker

    async def create_file(
        title: str,
        content: str,
        metadata_: dict | None = None,
        category: str | None = None,  # DocumentCategory как строку
        tags: list[str] | None = None,
    ) -> str:
        """Создать документ в БД для текущего пользователя."""
        from app.domain.enums.document import DocumentCategory
        from app.domain.models.document import Document as DocumentModel

        # Конвертируем category из строки в enum (case-insensitive + fallback)
        category_enum = None
        if category:
            try:
                # Пробуем lowercase версию (enum values are lowercase)
                category_enum = DocumentCategory(category.lower())
            except ValueError:
                # Если не сработало, пробуем маппинг для альтернативных названий
                category_map = {
                    "guide": "plan",
                    "note": "note",
                    "doc": "document",
                    "file": "document",
                    "snippet": "code",
                }
                mapped = category_map.get(category.lower())
                if mapped:
                    try:
                        category_enum = DocumentCategory(mapped)
                    except ValueError:
                        pass  # оставляем None

        # Создаём новую сессию для этого вызова (изолируем транзакцию)
        async with async_session_maker() as session:
            document = DocumentModel(
                user_id=user_id,  # ← из замыкания
                title=title,
                content=content,
                metadata_=metadata_,
                category=category_enum,
                tags=tags,
            )

            session.add(document)
            await session.commit()
            await session.refresh(document)

            return f"Документ создан с ID: {document.id}, заголовок: {title}"

    return create_file


def make_search_documents_tool(user_id: UUID) -> Callable[..., Awaitable[str]]:
    """Создаёт функцию search_documents с захваченным user_id."""
    from app.infrastructure.database.dependencies import async_session_maker

    async def search_documents(
        query: str,
        category: str | None = None,
        limit: int = 5,
        offset: int = 0,
    ) -> str:
        """Поиск по документам пользователя."""
        from app.application.services.document_service import DocumentService
        from app.domain.enums.document import DocumentCategory

        category_enum = None
        if category:
            try:
                category_enum = DocumentCategory(category.lower())
            except ValueError:
                pass

        async with async_session_maker() as session:
            from app.infrastructure.persistence.sqlalchemy.document_repository import DocumentSQLAlchemyRepository

            repository = DocumentSQLAlchemyRepository(session)
            service = DocumentService(repository)
            response = await service.search_user_documents(
                query=query,
                limit=limit,
                offset=offset,
                category=category_enum,
                current_user_id=user_id,
            )

        if not response.documents:
            return f"Документы по запросу '{query}' не найдены"

        lines = [f"Найдено {len(response.documents)} документов по запросу '{query}':\n"]
        for doc in response.documents:
            lines.append(f"ID: {doc.id}")
            lines.append(f"Заголовок: {doc.title or 'Без названия'}")
            lines.append(f"Категория: {doc.category}")
            lines.append(f"Релевантность: {doc.relevance_score:.2f}")
            if doc.summary:
                lines.append(f"Описание: {doc.summary}")
            if doc.tags:
                lines.append(f"Теги: {', '.join(doc.tags)}")
            lines.append("---")

        return "\n".join(lines)

    return search_documents


# --- Схема инструмента ---

WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web using DuckDuckGo",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {
                    "type": "integer",
                    "description": "Results (1-10)",
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["query"],
        },
    },
}


WEB_FETCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_fetch",
        "description": "Extract content from URLs.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
                "extract_mode": {
                    "type": "string",
                    "enum": ["markdown", "text"],
                    "default": "markdown",
                },
                "max_chars": {"type": "integer", "minimum": 100},
                "accept_markdown": {
                    "type": "boolean",
                    "default": False,
                    "description": "Request text/markdown from Cloudflare and other compatible sites",
                },
            },
            "required": ["url"],
        },
    },
}

CREATE_DOCUMENT_TOOL = {
    "type": "function",
    "function": {
        "name": "create_file",
        "description": "Save important information as a document in the user's knowledge base. Use this when the user asks to save, remember, or store information for later access.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "A clear, descriptive title for the document (e.g., 'Python asyncio guide', 'Meeting notes 2026-02-26')",
                },
                "content": {
                    "type": "string",
                    "description": "The main content to be saved - can be text, code, notes, summaries, or any other information",
                },
                "category": {
                    "type": "string",
                    "enum": ["note", "document", "plan", "code", "research", "summary", "template"],
                    "description": "Document type: 'note' for quick notes, 'document' for general content, 'plan' for action plans, 'code' for code snippets, 'research' for research findings, 'summary' for summaries, 'template' for reusable templates",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional keywords for easy searching later (e.g., ['python', 'asyncio', 'tutorial'])",
                },
            },
            "required": ["title", "content"],
        },
    },
}

FILE_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_documents",
        "description": "Search through user's documents, notes, guides and other saved materials. Use when user asks to find, recall or look up something from their knowledge base.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query — what to find (e.g., 'asyncio tasks', 'meeting notes')",
                },
                "category": {
                    "type": "string",
                    "enum": ["note", "document", "plan", "code", "research", "summary", "template"],
                    "description": "Optional filter by document type",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of results to return (default: 5)",
                    "minimum": 1,
                    "maximum": 20,
                },
            },
            "required": ["query"],
        },
    },
}


TOOLS = {"web_search": web_search, "web_fetch": web_fetch}
