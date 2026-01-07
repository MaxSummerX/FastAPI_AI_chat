import json
import os
from pathlib import Path
from uuid import UUID

import aiofiles
from loguru import logger
from sqlalchemy import select

from app.database.postgres_db import async_session_maker
from app.models.conversations import Conversation as ConversationModel
from app.models.messages import Message as MessageModel
from app.models.messages import MessageRole
from app.utils.gpt_history_converter import split_conversations_async


async def convert_gtp(user_id: UUID, provider: str, path: Path, input_file: str, output_dir: str) -> None:
    await split_conversations_async(input_file, output_dir)

    files = [i for i in path.iterdir() if i.is_file()]

    for item in files:
        try:
            async with aiofiles.open(item, encoding="utf-8") as f:
                content = await f.read()
                conversations = json.loads(content)

                async with async_session_maker() as session:
                    conversation = await session.scalar(
                        select(ConversationModel).where(
                            ConversationModel.user_id == user_id,
                            ConversationModel.source == "ChatGPT",
                            ConversationModel.source_id == conversations["id"],
                        )
                    )

                    if conversation:
                        logger.info(f"Беседа {item.name} уже существует. Удаляем исходный файл.")
                        os.remove(item)
                        continue

                    conversation = ConversationModel(
                        user_id=user_id,
                        title=conversations["title"],
                        source="ChatGPT",
                        source_id=conversations["id"],
                        is_imported=True,
                    )
                    session.add(conversation)
                    await session.commit()
                    await session.refresh(conversation)

                    for msg_data in conversations["mapping"]:
                        conversation_id = conversation.id

                        message = conversations["mapping"][msg_data]["message"]

                        if message:
                            if message["author"]["role"] == "user":
                                role = MessageRole.USER
                            else:
                                role = MessageRole.ASSISTANT

                            if message["content"]["content_type"] == "text":
                                if message["content"]["parts"] != [""]:
                                    msg = MessageModel(
                                        conversation_id=conversation_id,
                                        role=role,
                                        content=message["content"]["parts"][0],
                                        source="ChatGPT",
                                        source_id=message["id"],
                                        is_imported=True,
                                        model="ChatGPT",
                                        metadata_=message["metadata"],
                                    )
                                    session.add(msg)
                                    await session.commit()
            os.remove(item)
            logger.info(f"Файл {item.name} успешно обработан и удален")

        except Exception as e:
            logger.error(f"Ошибка при обработке файла {item.name}: {e}")

    if path.exists():
        os.rmdir(path)
