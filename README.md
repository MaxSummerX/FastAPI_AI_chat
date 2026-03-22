# FastAPI_AI_chat

Асинхронный AI-aгент с **системой памяти** и **анализом вакансий**. Извлекает и использует факты о пользователе для персонализированного контекста беседы.

🚧 **pet-project** для изучения AI-архитектур, FastAPI и современных Python паттернов


## ✨ Особенности

### Ядро
- **Система памяти** — mem0ai (управление) + Qdrant (вектора) + Neo4j (графы) + Ollama (эмбеддинги nomic-embed-text)
- **LLM Agent Tools** — search_documents, create_file, web_search, fetch_url (инструменты для AI агента)
- **Streaming ответы** — ответ LLM в реальном времени с поддержкой tool calling
- **JWT авторизация** — access/refresh токены с bcrypt хешированием
- **Полнотекстовый поиск** — TSVECTOR (PostgreSQL) для поиска по документам
- **Custom Prompts** — пользовательские системные промпты для кастомизации поведения

### Интеграции
- **hh.ru** — парсинг вакансий c актуализацией статуса
- **AI анализ** — анализ вакансий по типам (matching, prioritization, skill_gap, red_flags)
- **Импорт диалогов** — Claude.ai и GPT

### Архитектура
- **Асинхронный** — FastAPI + asyncio
- **Service Layer** — MessageService, DocumentService, FactService (частичная реализация)
- **Dependency Injection** — сессии БД, сервисы, LLM через зависимости
- **PostgreSQL** — SQLAlchemy 2.0 async + TSVECTOR полнотекстовый поиск
- **Курсорная пагинация** — стабильная и производительная (paginate_with_cursor)
- **Task Queue** — Celery + Redis для фоновых задач
- **Docker Compose** — production ready


## 🛠️ Технологический стек

| Категория | Технологии                                        |
|----------|---------------------------------------------------|
| **Backend** | FastAPI 0.120+, Uvicorn, Pydantic 2.12+           |
| **Database** | PostgreSQL, Qdrant, Neo4j, Redis                  |
| **ORM** | SQLAlchemy 2.0 async, Alembic                     |
| **Memory/AI** | mem0ai, OpenAI/OpenRouter, Ollama, langchain-neo4j |
| **Search** | TSVECTOR (PostgreSQL full-text search)            |
| **Web** | ddgs (DuckDuckGo), readability-lxml               |
| **Task Queue** | Celery + Redis                                    |
| **Testing** | pytest, pytest-asyncio, pytest-cov, pytest-mock   |
| **Linting** | ruff 0.15+, mypy, bandit, pre-commit              |
| **Deployment** | Docker, Docker Compose                           |


## ⚠️ Важно

Это **учебный pet-проект** для исследования современных архитектур и технологий. Может содержать:
- Незавершённую функциональность
- TODO комментарии
- Экспериментальные паттерны кода

## 📚 Изучаемые технологии

- Асинхронное программирование (asyncio)
- FastAPI и его возможности
- Интеграция с LLM (OpenAI, OpenRouter)
- Векторные базы данных (Qdrant)
- Графовые базы данных (Neo4j)
- Архитектура систем с памятью
- SQLAlchemy 2.0 async
- Docker и Docker Compose
- Курсорная пагинация
- Сервисная архитектура (Service Layer)
- LLM Agent Tools
- Полнотекстовый поиск (PostgreSQL TSVECTOR)

## Лицензия

MIT — подробности в файле [LICENSE](LICENSE)
