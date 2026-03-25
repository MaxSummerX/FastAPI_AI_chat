"""
Роли участников диалога.

Определяет автора сообщения в беседе.
"""

from enum import StrEnum


class MessageRole(StrEnum):
    """
    Роли участников диалога.

    Attributes:
        USER: Сообщение от пользователя
        ASSISTANT: Ответ от AI-ассистента
        SYSTEM: Системное сообщение
    """

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
