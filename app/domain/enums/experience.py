"""
Уровни опыта работы для вакансий.

Соответствует градации на hh.ru от нет опыта до более 6 лет.
Также используется для сортировки вакансий.
"""

from enum import StrEnum


class Experience(StrEnum):
    """
    Уровни опыта работы.

    Attributes:
        NO_EXPERIENCE: Нет опыта
        BETWEEN_1_AND_3: От 1 до 3 лет
        BETWEEN_3_AND_6: От 3 до 6 лет
        MORE_THAN_6: Более 6 лет
    """

    NO_EXPERIENCE = "noExperience"
    BETWEEN_1_AND_3 = "between1And3"
    BETWEEN_3_AND_6 = "between3And6"
    MORE_THAN_6 = "moreThan6"


class OrderField(StrEnum):
    """
    Поля для сортировки вакансий.

    Attributes:
        CREATED_AT: По дате создания
        PUBLISHED_AT: По дате публикации
    """

    CREATED_AT = "created_at"
    PUBLISHED_AT = "published_at"
