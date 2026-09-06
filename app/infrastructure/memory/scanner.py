"""
Прямой скролл точек Qdrant для сверки с PG.
"""

from uuid import UUID

from qdrant_client import AsyncQdrantClient

from app.infrastructure.memory.config import QDRANT_API_KEY, QDRANT_BASE_URL, QDRANT_COLLECTION_NAME


SCROLL_BATCH = 256  # размер страницы скролла Qdrant


class QdrantPointScanner:
    """
    Читает id всех точек коллекции Qdrant (read-only).
    """

    def __init__(self) -> None:
        """
        Инициализирует отдельный клиент Qdrant.

        api_key=None для локального Qdrant без авторизации.
        """
        self._client = AsyncQdrantClient(url=QDRANT_BASE_URL, api_key=QDRANT_API_KEY)

    async def get_all_points_ids(self) -> set[UUID]:
        """
        Скроллит коллекцию пачками и собирает id всех точек.

        Returns:
            Множество id точек коллекции.
        """
        ids: set[UUID] = set()
        offset: int | str | UUID | None = None

        while True:
            points, offset = await self._client.scroll(
                collection_name=QDRANT_COLLECTION_NAME,
                limit=SCROLL_BATCH,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            for point in points:
                point_id = point.id
                ids.add(point_id if isinstance(point_id, UUID) else UUID(str(point_id)))
            if offset is None:
                break
        return ids

    async def close(self) -> None:
        """Закрывает httpx-клиент Qdrant. Вызывать после использования."""
        await self._client.close()
