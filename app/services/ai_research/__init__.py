"""
AI-анализ вакансий через LLM.

Предоставляет функции для анализа вакансий с различными типами:
- matching: соответствие кандидата вакансии
- prioritization: оценка привлекательности
- preparation: подготовка к интервью
- skill_gap: анализ пробелов в навыках
- custom: пользовательский промпт
"""

from app.services.ai_research.analyzer import analyze_vacancy_from_db
from app.services.ai_research.parallel import ai_response_gather
from app.services.ai_research.utils import prompt_choice


__all__ = [
    # Анализ вакансий
    "analyze_vacancy_from_db",
    # Промпты
    "prompt_choice",
    # Параллельные запросы
    "ai_response_gather",
]
