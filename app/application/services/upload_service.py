import asyncio
from pathlib import Path
from uuid import UUID

from loguru import logger

from app.domain.repositories.conversations import IConversationRepository
from app.domain.repositories.messages import IMessageRepository
from app.infrastructure.upload.converters.claude_split_conversations_async import claude_split_conversations_async
from app.infrastructure.upload.converters.gpt_history_converter import gpt_split_conversations_async
from app.infrastructure.upload.converters.parser_claude import parse_claude
from app.infrastructure.upload.converters.parser_gpt import parse_gtp


class UploadService:
    def __init__(self, conversation_repo: IConversationRepository, message_repo: IMessageRepository) -> None:
        """ """
        self.conversation_repo = conversation_repo
        self.message_repo = message_repo

    async def import_from_claude(self, user_id: UUID, provider: str, file_path: Path, split_dir: Path) -> None:
        await claude_split_conversations_async(str(file_path), str(split_dir))
        results = await asyncio.to_thread(parse_claude, user_id, provider, split_dir)
        await self._save_result(results, provider, user_id)

    async def import_from_gpt(self, user_id: UUID, provider: str, file_path: Path, split_dir: Path) -> None:
        await gpt_split_conversations_async(str(file_path), str(split_dir))
        results = await asyncio.to_thread(parse_gtp, user_id, provider, split_dir)
        await self._save_result(results, provider, user_id)

    async def _save_result(self, results: list, provider: str, user_id: UUID) -> None:
        for conversation, messages in results:
            existing = await self.conversation_repo.get_by_source_id_and_source(
                provider, conversation.source_id, user_id
            )
            if existing:
                logger.info(f"Found existing conversation {conversation.source_id}")
                continue
            await self.conversation_repo.save_from_import(conversation)
            await self.message_repo.save_all(messages)
