from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass
class StreamData:
    """DTO для данных потокового ответа."""

    stream: AsyncIterator[str]
    result_awaitable: Awaitable[dict[str, Any]]
    conversation_id: UUID
    model: str
    history: list[dict]
    tools: dict[str, Callable[..., Any]]
