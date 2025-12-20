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
from app.utils.split_conversations_async import split_conversations_async


async def convert(user_id: UUID, provider: str, path: Path, input_file: str, output_dir: str) -> None:
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
                            ConversationModel.source == "CLAUDE",
                            ConversationModel.source_id == conversations["uuid"],
                        )
                    )

                    if conversation:
                        logger.info(f"Беседа {item.name} уже существует. Удаляем исходный файл.")
                        os.remove(item)
                        continue

                    conversation = ConversationModel(
                        user_id=user_id,
                        title=conversations["name"],
                        source="CLAUDE",
                        source_id=conversations["uuid"],
                        is_imported=True,
                    )
                    session.add(conversation)
                    await session.commit()
                    await session.refresh(conversation)

                    for msg in conversations["chat_messages"]:
                        uuid_id = msg["uuid"]
                        conversation_id = conversation.id

                        if msg["sender"] == "human":
                            role = MessageRole.USER

                            for content in msg["content"]:
                                if isinstance(content, dict) and content.get("text"):
                                    message = MessageModel(
                                        conversation_id=conversation_id,
                                        role=role,
                                        content=content["text"],
                                        source="CLAUDE",
                                        source_id=uuid_id,
                                        is_imported=True,
                                        model="Claude",
                                        metadata_={
                                            "data_type": "user_message",
                                            "flags": content["flags"],
                                            "type": content["type"],
                                        },
                                    )
                                    session.add(message)
                                    await session.commit()

                            for attachment in msg["attachments"]:
                                if attachment:
                                    message = MessageModel(
                                        conversation_id=conversation_id,
                                        role=role,
                                        content=attachment["extracted_content"],
                                        source="CLAUDE",
                                        source_id=uuid_id,
                                        is_imported=True,
                                        model="Claude",
                                        metadata_={
                                            "data_type": "user_attachment",
                                            "file_name": attachment["file_name"],
                                            "file_size": attachment["file_size"],
                                            "file_type": attachment["file_type"],
                                        },
                                    )
                                    session.add(message)
                                    await session.commit()
                        else:
                            role = MessageRole.ASSISTANT

                            for content in msg["content"]:
                                if isinstance(content, dict) and content.get("input"):
                                    if content["input"].get("content"):
                                        message = MessageModel(
                                            conversation_id=conversation_id,
                                            role=role,
                                            content=content["input"]["content"],
                                            source="CLAUDE",
                                            source_id=uuid_id,
                                            is_imported=True,
                                            model="Claude",
                                            metadata_={
                                                "data_type": "Claude_message",
                                                "flags": content["flags"],
                                                "type": content["type"],
                                                "name": content["name"],
                                            },
                                        )
                                        session.add(message)
                                        await session.commit()
                                    if content["input"].get("new_str"):
                                        message = MessageModel(
                                            conversation_id=conversation_id,
                                            role=role,
                                            content=content["input"]["new_str"],
                                            source="CLAUDE",
                                            source_id=uuid_id,
                                            is_imported=True,
                                            model="Claude",
                                            metadata_={
                                                "data_type": "Claude_message",
                                                "flags": content["flags"],
                                                "type": content["type"],
                                                "name": content["name"],
                                            },
                                        )
                                        session.add(message)
                                        await session.commit()

                                if isinstance(content, dict) and content.get("content"):
                                    for data in content["content"]:
                                        message = MessageModel(
                                            conversation_id=conversation_id,
                                            role=role,
                                            content=data["text"],
                                            source="CLAUDE",
                                            source_id=uuid_id,
                                            is_imported=True,
                                            model="Claude",
                                            metadata_={
                                                "data_type": "Claude_message",
                                                "flags": content["flags"],
                                                "type": content["type"],
                                                "name": content["name"],
                                            },
                                        )
                                        session.add(message)
                                        await session.commit()

                                if isinstance(content, dict) and content.get("text"):
                                    message = MessageModel(
                                        conversation_id=conversation_id,
                                        role=role,
                                        content=content["text"],
                                        source="CLAUDE",
                                        source_id=uuid_id,
                                        is_imported=True,
                                        model="Claude",
                                        metadata_={
                                            "data_type": "Claude_message",
                                            "flags": content["flags"],
                                            "type": content["type"],
                                        },
                                    )
                                    session.add(message)
                                    await session.commit()
            os.remove(item)
            logger.info(f"Файл {item.name} успешно обработан и удален")

        except Exception as e:
            logger.error(f"Ошибка при обработке файла {item.name}: {e}")

    if path.exists():
        os.rmdir(path)
