import json
from pathlib import Path
from uuid import UUID, uuid4

from loguru import logger

from app.domain.models.conversation import Conversation as ConversationModel
from app.domain.models.message import Message as MessageModel
from app.domain.models.message import MessageRole


def parse_claude(user_id: UUID, provider: str, path: Path) -> list[tuple[ConversationModel, list[MessageModel]]]:
    conversations = []
    for item in path.iterdir():
        if not item.is_file():
            continue
        try:
            data = json.loads(item.read_text(encoding="utf-8"))
            conversation = ConversationModel(
                id=uuid4(),
                user_id=user_id,
                title=data["name"],
                source=provider,
                source_id=data["uuid"],
                is_imported=True,
            )
            messages = []

            for msg in data["chat_messages"]:
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
                            messages.append(message)

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
                            messages.append(message)
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
                                messages.append(message)
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
                                messages.append(message)

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
                                messages.append(message)

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
                            messages.append(message)

            conversations.append((conversation, messages))

        except Exception as e:
            logger.error(f"Ошибка при обработке файла {item.name}: {e}")

    return conversations
