from enum import Enum


class ImportedProvider(str, Enum):
    GPT = "gpt"
    CLAUDE = "claude"
