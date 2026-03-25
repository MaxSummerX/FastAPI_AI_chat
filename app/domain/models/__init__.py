"""
Domain models (ORM сущности).

Модуль содержит все domain entities приложения на SQLAlchemy.
Каждая модель представляет бизнес-сущность предметной области
и определяется независимо от персистентного слоя (Repository pattern).

Models:
    User: Пользователь системы
    Conversation: Диалог/сессия чата
    Message: Сообщение в чате
    Fact: Факт о пользователе
    Prompts: Кастомный промпт
    Document: Документ пользователя
    Vacancy: Вакансия с hh.ru
    Invite: Инвайт-код для регистрации
    VacancyAnalysis: LLM анализ вакансии
    UserVacancies: Связь пользователя с вакансией
"""

from .conversation import Conversation
from .document import Document
from .fact import Fact
from .invite import Invite
from .message import Message
from .prompt import Prompts
from .user import User
from .user_vacancies import UserVacancies
from .vacancy import Vacancy
from .vacancy_analysis import VacancyAnalysis


__all__ = [
    "User",
    "Conversation",
    "Message",
    "Fact",
    "Prompts",
    "Vacancy",
    "Invite",
    "VacancyAnalysis",
    "UserVacancies",
    "Document",
]
