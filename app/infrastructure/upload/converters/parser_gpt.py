import json
from pathlib import Path
from uuid import UUID, uuid4

from loguru import logger

from app.domain.models.conversation import Conversation as ConversationModel
from app.domain.models.message import Message as MessageModel
from app.domain.models.message import MessageRole


def parse_gtp(user_id: UUID, provider: str, path: Path) -> list[tuple[ConversationModel, list[MessageModel]]]:
    conversations = []
    for item in path.iterdir():
        if not item.is_file():
            continue
        try:
            data = json.loads(item.read_text(encoding="utf-8"))
            conversation = ConversationModel(
                id=uuid4(),
                user_id=user_id,
                title=data["title"],
                source=provider,
                source_id=data["id"],
                is_imported=True,
            )
            messages = []
            for msg_data in data["mapping"]:
                conversation_id = conversation.id
                message = data["mapping"][msg_data]["message"]

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
                            messages.append(msg)
            conversations.append((conversation, messages))

        except Exception as e:
            logger.error(f"Ошибка при обработке файла {item.name}: {e}")

    return conversations
