"""
Тесты для AnalysisType enum.

Проверяет:
- Значения всех типов анализа
- Свойства display_name и description
- Методы класса: builtin_types(), is_builtin()
- Метод __str__
"""

import pytest

from app.enum.analysis import AnalysisType


# ============================================================
# Тесты значений enum
# ============================================================


def test_analysis_type_values() -> None:
    """Тест: проверка что все типы имеют правильные строковые значения"""
    assert AnalysisType.MATCHING.value == "matching"
    assert AnalysisType.PRIORITIZATION.value == "prioritization"
    assert AnalysisType.PREPARATION.value == "preparation"
    assert AnalysisType.SKILL_GAP.value == "skill_gap"
    assert AnalysisType.CUSTOM.value == "custom"


def test_analysis_type_count() -> None:
    """Тест: проверка что в enum 5 типов"""
    assert len(AnalysisType) == 5


def test_analysis_type_from_string() -> None:
    """Тест: создание enum из строки"""
    assert AnalysisType("matching") == AnalysisType.MATCHING
    assert AnalysisType("prioritization") == AnalysisType.PRIORITIZATION
    assert AnalysisType("preparation") == AnalysisType.PREPARATION
    assert AnalysisType("skill_gap") == AnalysisType.SKILL_GAP
    assert AnalysisType("custom") == AnalysisType.CUSTOM


def test_analysis_type_invalid_string() -> None:
    """Тест: создание enum из невалидной строки вызывает ValueError"""
    with pytest.raises(ValueError):
        AnalysisType("invalid_type")


# ============================================================
# Тесты свойства display_name
# ============================================================


def test_display_name_matching() -> None:
    """Тест: display_name для MATCHING"""
    assert AnalysisType.MATCHING.display_name == "Соответствие вакансии"


def test_display_name_prioritization() -> None:
    """Тест: display_name для PRIORITIZATION"""
    assert AnalysisType.PRIORITIZATION.display_name == "Оценка привлекательности"


def test_display_name_preparation() -> None:
    """Тест: display_name для PREPARATION"""
    assert AnalysisType.PREPARATION.display_name == "Подготовка к интервью"


def test_display_name_skill_gap() -> None:
    """Тест: display_name для SKILL_GAP"""
    assert AnalysisType.SKILL_GAP.display_name == "Анализ навыков"


def test_display_name_custom() -> None:
    """Тест: display_name для CUSTOM"""
    assert AnalysisType.CUSTOM.display_name == "Кастомный анализ"


def test_display_name_all_unique() -> None:
    """Тест: все display_name уникальны"""
    display_names = [t.display_name for t in AnalysisType]
    assert len(display_names) == len(set(display_names))


# ============================================================
# Тесты свойства description
# ============================================================


def test_description_matching() -> None:
    """Тест: description для MATCHING"""
    desc = AnalysisType.MATCHING.description
    assert "кандидат" in desc.lower()
    assert "вакансии" in desc.lower()


def test_description_prioritization() -> None:
    """Тест: description для PRIORITIZATION"""
    desc = AnalysisType.PRIORITIZATION.description
    assert "привлекатель" in desc.lower() or "отклик" in desc.lower()


def test_description_preparation() -> None:
    """Тест: description для PREPARATION"""
    desc = AnalysisType.PREPARATION.description
    assert "собеседован" in desc.lower() or "интервью" in desc.lower()


def test_description_skill_gap() -> None:
    """Тест: description для SKILL_GAP"""
    desc = AnalysisType.SKILL_GAP.description
    assert "навык" in desc.lower() or "пробел" in desc.lower()


def test_description_custom() -> None:
    """Тест: description для CUSTOM"""
    desc = AnalysisType.CUSTOM.description
    assert "пользователь" in desc.lower() or "custom" in desc.lower()


def test_description_all_non_empty() -> None:
    """Тест: все description непустые"""
    for analysis_type in AnalysisType:
        assert analysis_type.description
        assert len(analysis_type.description) > 0


# ============================================================
# Тесты метода builtin_types()
# ============================================================


def test_builtin_types_returns_list() -> None:
    """Тест: builtin_types() возвращает список"""
    builtin = AnalysisType.builtin_types()
    assert isinstance(builtin, list)


def test_builtin_types_count() -> None:
    """Тест: builtin_types() возвращает 4 типа (без CUSTOM)"""
    builtin = AnalysisType.builtin_types()
    assert len(builtin) == 4


def test_builtin_types_content() -> None:
    """Тест: builtin_types() содержит правильные типы"""
    builtin = AnalysisType.builtin_types()
    assert AnalysisType.MATCHING in builtin
    assert AnalysisType.PRIORITIZATION in builtin
    assert AnalysisType.PREPARATION in builtin
    assert AnalysisType.SKILL_GAP in builtin
    assert AnalysisType.CUSTOM not in builtin


def test_builtin_types_all_are_builtin() -> None:
    """Тест: все типы из builtin_types() помечены как builtin"""
    builtin = AnalysisType.builtin_types()
    for analysis_type in builtin:
        assert analysis_type in AnalysisType.builtin_types()


# ============================================================
# Тесты метода is_builtin()
# ============================================================


def test_is_builtin_matching() -> None:
    """Тест: is_builtin() для MATCHING возвращает True"""
    assert AnalysisType.is_builtin("matching") is True


def test_is_builtin_prioritization() -> None:
    """Тест: is_builtin() для PRIORITIZATION возвращает True"""
    assert AnalysisType.is_builtin("prioritization") is True


def test_is_builtin_preparation() -> None:
    """Тест: is_builtin() для PREPARATION возвращает True"""
    assert AnalysisType.is_builtin("preparation") is True


def test_is_builtin_skill_gap() -> None:
    """Тест: is_builtin() для SKILL_GAP возвращает True"""
    assert AnalysisType.is_builtin("skill_gap") is True


def test_is_builtin_custom() -> None:
    """Тест: is_builtin() для CUSTOM возвращает False"""
    assert AnalysisType.is_builtin("custom") is False


def test_is_builtin_invalid_string() -> None:
    """Тест: is_builtin() для невалидной строки возвращает False"""
    assert AnalysisType.is_builtin("invalid_type") is False


def test_is_builtin_case_sensitive() -> None:
    """Тест: is_builtin() чувствителен к регистру"""
    assert AnalysisType.is_builtin("Matching") is False
    assert AnalysisType.is_builtin("MATCHING") is False
    assert AnalysisType.is_builtin("matching") is True


# ============================================================
# Тесты метода __str__
# ============================================================


def test_str_matching() -> None:
    """Тест: __str__ для MATCHING"""
    assert str(AnalysisType.MATCHING) == "matching"


def test_str_prioritization() -> None:
    """Тест: __str__ для PRIORITIZATION"""
    assert str(AnalysisType.PRIORITIZATION) == "prioritization"


def test_str_preparation() -> None:
    """Тест: __str__ для PREPARATION"""
    assert str(AnalysisType.PREPARATION) == "preparation"


def test_str_skill_gap() -> None:
    """Тест: __str__ для SKILL_GAP"""
    assert str(AnalysisType.SKILL_GAP) == "skill_gap"


def test_str_custom() -> None:
    """Тест: __str__ для CUSTOM"""
    assert str(AnalysisType.CUSTOM) == "custom"


def test_str_equals_value() -> None:
    """Тест: __str__ возвращает то же что и .value"""
    for analysis_type in AnalysisType:
        assert str(analysis_type) == analysis_type.value


# ============================================================
# Интеграционные тесты
# ============================================================


def test_enum_iteration() -> None:
    """Тест: итерация по всем типам enum"""
    types = list(AnalysisType)
    assert len(types) == 5
    assert AnalysisType.MATCHING in types
    assert AnalysisType.PRIORITIZATION in types
    assert AnalysisType.PREPARATION in types
    assert AnalysisType.SKILL_GAP in types
    assert AnalysisType.CUSTOM in types


def test_enum_comparison() -> None:
    """Тест: сравнение enum значений"""
    assert AnalysisType.MATCHING == AnalysisType.MATCHING
    assert AnalysisType.MATCHING != AnalysisType.PRIORITIZATION
    assert AnalysisType.MATCHING == "matching"


def test_enum_hashable() -> None:
    """Тест: enum значения можно использовать в set и как ключи dict"""
    types_set = {AnalysisType.MATCHING, AnalysisType.PRIORITIZATION}
    assert len(types_set) == 2

    types_dict = {AnalysisType.MATCHING: "value1"}
    assert types_dict[AnalysisType.MATCHING] == "value1"


def test_enum_order_consistent() -> None:
    """Тест: порядок enum значений соответствует определению"""
    types = list(AnalysisType)
    assert types[0] == AnalysisType.MATCHING
    assert types[1] == AnalysisType.PRIORITIZATION
    assert types[2] == AnalysisType.PREPARATION
    assert types[3] == AnalysisType.SKILL_GAP
    assert types[4] == AnalysisType.CUSTOM


# ============================================================
# Параметризованные тесты для всех типов
# ============================================================


@pytest.mark.parametrize(
    "analysis_type,expected_value,expected_display",
    [
        (AnalysisType.MATCHING, "matching", "Соответствие вакансии"),
        (AnalysisType.PRIORITIZATION, "prioritization", "Оценка привлекательности"),
        (AnalysisType.PREPARATION, "preparation", "Подготовка к интервью"),
        (AnalysisType.SKILL_GAP, "skill_gap", "Анализ навыков"),
        (AnalysisType.CUSTOM, "custom", "Кастомный анализ"),
    ],
)
def test_all_types_properties(analysis_type: AnalysisType, expected_value: str, expected_display: str) -> None:
    """Параметризованный тест: проверка свойств для всех типов"""
    assert analysis_type.value == expected_value
    assert analysis_type.display_name == expected_display
    assert str(analysis_type) == expected_value
    assert len(analysis_type.description) > 0


@pytest.mark.parametrize(
    "value,is_builtin_expected",
    [
        ("matching", True),
        ("prioritization", True),
        ("preparation", True),
        ("skill_gap", True),
        ("custom", False),
        ("invalid", False),
    ],
)
def test_is_builtin_parametrized(value: str, is_builtin_expected: bool) -> None:
    """Параметризованный тест: проверка is_builtin для всех значений"""
    assert AnalysisType.is_builtin(value) == is_builtin_expected
