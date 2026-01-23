from app.enum.analysis import AnalysisType
from app.prompts.prompts_for_analysis import (
    MATCHING_PROMPT,
    PREPARATION_PROMPT,
    PRIORITIZATION_PROMPT,
    SKILL_GAP_PROMPT,
)
from app.tools.ai_research.exceptions import InvalidAnalysisTypeError


def prompt_choice(analysis_type: AnalysisType) -> tuple[str, bool]:
    """
    Возвращает промпт для указанного типа анализа.

    Args:
        analysis_type: Тип анализа

    Returns:
        Кортеж (промпт, нужен_ли_резюме)

    Raises:
        InvalidAnalysisTypeError: Если тип анализа не поддерживается
    """
    match analysis_type:
        case AnalysisType.MATCHING:
            return MATCHING_PROMPT, True
        case AnalysisType.SKILL_GAP:
            return SKILL_GAP_PROMPT, True
        case AnalysisType.PREPARATION:
            return PREPARATION_PROMPT, False
        case AnalysisType.PRIORITIZATION:
            return PRIORITIZATION_PROMPT, False
        case _:
            raise InvalidAnalysisTypeError(f"Неподдерживаемый тип анализа: {analysis_type}")
