"""
Категории документов в системе.

Используется для классификации пользовательских документов.
"""

from enum import StrEnum


class DocumentCategory(StrEnum):
    """
    Категории документов.

    Attributes:
        NOTE: Заметка, мысль
        DOCUMENT: Полноценный структурированный документ
        PLAN: План, задачи, roadmap
        CODE: Код, сниппет, техническое решение
        RESEARCH: Анализ, исследование, обзор
        SUMMARY: Саммари беседы или материала
        TEMPLATE: Шаблон для переиспользования
    """

    NOTE = "note"
    DOCUMENT = "document"
    PLAN = "plan"
    CODE = "code"
    RESEARCH = "research"
    SUMMARY = "summary"
    TEMPLATE = "template"
