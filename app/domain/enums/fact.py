"""
Категории и источники фактов о пользователях.

Используется для классификации информации в системе памяти.
"""

from enum import StrEnum


class FactCategory(StrEnum):
    """
    Категории фактов о пользователе.

    Attributes:
        PERSONAL: Личная информация
        PROFESSIONAL: Работа, навыки
        PREFERENCES: Предпочтения
        LEARNING: Что изучает
        GOALS: Цели
        INTERESTS: Интересы
        TECHNICAL: Технические знания
        BEHAVIORAL: Паттерны поведения
    """

    PERSONAL = "personal"
    PROFESSIONAL = "professional"
    PREFERENCES = "preferences"
    LEARNING = "learning"
    GOALS = "goals"
    INTERESTS = "interests"
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"


class FactSource(StrEnum):
    """
    Источник происхождения факта.

    Attributes:
        EXTRACTED: Автоматически извлечён из диалога
        USER_PROVIDED: Добавлен пользователем вручную
        IMPORTED: Импортирован из внешнего источника
        INFERRED: Выведен AI на основе нескольких фактов
    """

    EXTRACTED = "extracted"
    USER_PROVIDED = "user_provided"
    IMPORTED = "imported"
    INFERRED = "inferred"
