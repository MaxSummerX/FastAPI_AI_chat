from enum import StrEnum


class FactCategory(StrEnum):
    """Категории фактов"""

    PERSONAL = "personal"  # Личная информация
    PROFESSIONAL = "professional"  # Работа, навыки
    PREFERENCES = "preferences"  # Предпочтения
    LEARNING = "learning"  # Что изучает
    GOALS = "goals"  # Цели
    INTERESTS = "interests"  # Интересы
    TECHNICAL = "technical"  # Технические знания
    BEHAVIORAL = "behavioral"  # Паттерны поведения


class FactSource(StrEnum):
    """Источник факта"""

    EXTRACTED = "extracted"  # Автоматически извлечён из диалога
    USER_PROVIDED = "user_provided"  # Добавлен пользователем вручную
    IMPORTED = "imported"  # Импортирован из внешнего источника
    INFERRED = "inferred"  # Выведен AI на основе нескольких фактов
