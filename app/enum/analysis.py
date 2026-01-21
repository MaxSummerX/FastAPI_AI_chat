from enum import Enum


class AnalysisType(str, Enum):
    """
    Типы анализа вакансии от LLM.
    """

    MATCHING = "matching"  # Анализ соответствия кандидата вакансии
    PRIORITIZATION = "prioritization"  # Оценка привлекательности вакансии для отклика
    PREPARATION = "preparation"  # Подготовка к собеседованию
    SKILL_GAP = "skill_gap"  # Анализ пробелов в навыках
    CUSTOM = "custom"  # Пользовательский промпт

    def __str__(self) -> str:
        return self.value

    @classmethod
    def builtin_types(cls) -> list["AnalysisType"]:
        """Возвращает список встроенных типов анализа"""
        return [cls.MATCHING, cls.PRIORITIZATION, cls.PREPARATION, cls.SKILL_GAP]

    @classmethod
    def is_builtin(cls, value: str) -> bool:
        """Проверяет, является ли тип встроенным"""
        try:
            return cls(value) in cls.builtin_types()
        except ValueError:
            return False

    @property
    def display_name(self) -> str:
        """Человеко-читаемое название типа"""
        display_map = {
            self.MATCHING: "Соответствие вакансии",
            self.PRIORITIZATION: "Оценка привлекательности",
            self.PREPARATION: "Подготовка к интервью",
            self.SKILL_GAP: "Анализ навыков",
            self.CUSTOM: "Кастомный анализ",
        }
        return display_map.get(self, self.value)

    @property
    def description(self) -> str:
        """Описание типа анализа"""
        desc_map = {
            self.MATCHING: "Анализ того, насколько кандидат соответствует требованиям вакансии",
            self.PRIORITIZATION: "Оценка того, насколько стоит откликаться на эту вакансию",
            self.PREPARATION: "Рекомендации по подготовке к собеседованию",
            self.SKILL_GAP: "Анализ пробелов в навыках и что нужно изучить",
            self.CUSTOM: "Анализ по пользовательскому промпту",
        }
        return desc_map.get(self, "")
