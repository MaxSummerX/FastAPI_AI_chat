from enum import StrEnum


class MessageRole(StrEnum):
    """Роли участников диалога"""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
