from enum import StrEnum


class DocumentCategory(StrEnum):
    """Категории документов"""

    NOTE = "note"  # Заметка, мысль
    DOCUMENT = "document"  # Полноценный структурированный документ
    PLAN = "plan"  # План, задачи, roadmap
    CODE = "code"  # Код, сниппет, техническое решение
    RESEARCH = "research"  # Анализ, исследование, обзор
    SUMMARY = "summary"  # Саммари беседы или материала
    TEMPLATE = "template"  # Шаблон для переиспользования
