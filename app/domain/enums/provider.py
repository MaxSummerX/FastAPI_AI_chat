"""
Провайдеры импорта диалогов.

Определяет источники, из которых были импортированы диалоги.
"""

from enum import StrEnum


class ImportedProvider(StrEnum):
    """
    Провайдеры импорта диалогов.

    Attributes:
        GPT: Диалоги из ChatGPT
        CLAUDE: Диалоги из Claude.ai
    """

    GPT = "gpt"
    CLAUDE = "claude"
