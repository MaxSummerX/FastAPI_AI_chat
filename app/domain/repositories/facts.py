from abc import ABC, abstractmethod
from collections.abc import Sequence
from uuid import UUID

from app.domain.enums.fact import FactCategory, FactSource
from app.domain.models.fact import Fact


class IFactRepository(ABC):
    @abstractmethod
    async def get_paginated(
        self,
        user_id: UUID,
        cursor: str | None,
        limit: int,
        category: FactCategory | None = None,
        source: FactSource | None = None,
        include_archived: bool = False,
    ) -> tuple[Sequence[Fact], str | None, bool]:
        pass

    @abstractmethod
    async def get_by_id(self, fact_id: UUID, user_id: UUID) -> Fact | None:
        pass

    @abstractmethod
    async def create(
        self,
        user_id: UUID,
        content: str,
        category: FactCategory,
        source_type: FactSource,
        confidence: float,
        source_conversation_id: UUID | None = None,
        source_message_id: UUID | None = None,
        superseded_by_id: UUID | None = None,
        metadata_: dict | None = None,
        mem0_id: UUID | None = None,
    ) -> Fact:
        pass

    @abstractmethod
    async def update(self, fact_id: UUID, update_data: dict) -> None:
        pass

    @abstractmethod
    async def get_all_facts_by_source(self, user_id: UUID, source: FactSource) -> Sequence[Fact]:
        pass

    @abstractmethod
    async def save(self, fact: Fact) -> Fact:
        pass

    @abstractmethod
    async def save_all(self, facts: Sequence[Fact]) -> bool:
        pass
