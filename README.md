# FastAPI_AI_chat

Асинхронный AI-чат с **системой памяти** и **анализом вакансий**. Извлекает и использует факты о пользователе для персонализированного контекста беседы.

🚧 **pet-project** для изучения AI-архитектур, FastAPI и современных Python паттернов


## ✨ Особенности

### Ядро
- **Система памяти** — mem0ai + Qdrant + Neo4j + Ollama (nomic-embed-text)
- **Streaming ответы** — ответ LLM в реальном времени
- **JWT авторизация** — access/refresh токены
- **Документы** — заметки, планы, код с категоризацией и тегами

### Интеграции
- **hh.ru** — поиск и парсинг вакансий
- **AI анализ** — анализ вакансий по типам (matching, prioritization, skill_gap, red_flags)
- **Импорт диалогов** — Claude.ai и GPT

### Архитектура
- **Асинхронный** — FastAPI + asyncio
- **PostgreSQL** — SQLAlchemy 2.0 async
- **Курсорная пагинация** — стабильная и производительная
- **Docker Compose** — production ready


## 🛠️ Технологический стек

| Категория | Технологии                              |
|----------|-----------------------------------------|
| **Backend** | FastAPI 0.120+, Uvicorn, Pydantic 2.12+ |
| **Database** | PostgreSQL, Qdrant, Neo4j, Redis        |
| **ORM** | SQLAlchemy 2.0 async, Alembic           |
| **Memory/AI** | mem0ai, OpenAI/OpenRouter, Ollama       |
| **Testing** | pytest, pytest-asyncio                  |
| **Linting** | ruff, mypy, pre-commit                  |
| **Task Queue** | Celery + Redis                          |
| **Deployment** | Docker, Docker Compose                  |


## 📦 Установка

### Требования
- Python 3.13+
- PostgreSQL 16+
- Redis 7+
- mem0ai 1+
- Docker & Docker Compose (опционально)

### Через uv (рекомендуется)
```bash
git clone <repo>
cd FastAPI_AI_chat
uv sync
uv run uvicorn app.main:app --reload
```

### Через pip
```bash
pip install -e .
uvicorn app.main:app --reload
```

### Docker (Production)
```bash
make build
make up
make logs-app
```


## 🔧 Конфигурация

Создайте `.env` файл на основе `env.example`:

```bash
# Основные
SECRET_KEY=<сгенерируйте через python -c "import secrets; print(secrets.token_urlsafe(32))">
POSTGRESQL=postgresql+asyncpg://user:pass@localhost/dbname

# AI/LLM
OPENROUTER_API_KEY=<ключ>
OPENAI_API_KEY=<ключ>

# Memory systems
QDRANT_API_KEY=<ключ>
NEO4J_PASSWORD=<пароль>
API_MEM0_ONLINE=<ключ>

```


## 📚 API v2 Эндпоинты

### Аутентификация
```
POST   /api/v2/user/register               # Регистрация
POST   /api/v2/user/register_with_invite   # Регистрация с инвайтом
POST   /api/v2/user/token                  # Получить токен (логин)
POST   /api/v2/user/refresh-token          # Обновить access токен
GET    /api/v2/user                        # Базовая информация
GET    /api/v2/user/info                  # Полная информация
PATCH  /api/v2/user/update                # Обновить профиль
POST   /api/v2/user/update-email           # Обновить email
POST   /api/v2/user/update-password        # Обновить пароль
POST   /api/v2/user/update-username        # Обновить username
```

### Диалоги
```
GET    /api/v2/conversations          # Список с пагинацией
GET    /api/v2/conversations/{id}     # Получить диалог
POST   /api/v2/conversations          # Создать
PATCH  /api/v2/conversations/{id}     # Обновить
DELETE /api/v2/conversations/{id}     # Удалить
```

### Сообщения
```
GET    /api/v2/{conversation_id}/messages        # Сообщения с пагинацией
POST   /api/v2/{conversation_id}/messages/stream_v2  # Streaming ответ
```

### Факты (memory)
```
GET    /api/v2/facts                # Список с пагинацией
GET    /api/v2/facts/{id}           # Получить факт
POST   /api/v2/facts                # Создать
PUT    /api/v2/facts/{id}           # Обновить
DELETE /api/v2/facts/{id}           # Удалить (мягкое)
POST   /api/v2/facts/import_facts   # Импортировать факты
```

### Промпты
```
GET    /api/v2/prompts               # Список с пагинацией
GET    /api/v2/prompts/{id}          # Получить промпт
POST   /api/v2/prompts               # Создать
PUT    /api/v2/prompts/{id}          # Обновить
DELETE /api/v2/prompts/{id}          # Удалить (мягкое)
```

### Документы
```
GET    /api/v2/documents             # Список с пагинацией
GET    /api/v2/documents/{id}        # Получить документ
POST   /api/v2/documents             # Создать
PATCH  /api/v2/documents/{id}        # Обновить
DELETE /api/v2/documents/{id}        # Удалить (мягкое)
```

### Вакансии
```
GET    /api/v2/vacancies                  # Список вакансий
POST   /api/v2/vacancies                  # Добавить по hh_id
GET    /api/v2/vacancies/{id}             # Получить вакансию
PUT    /api/v2/vacancies/{id}/favorite     # В избранное
DELETE /api/v2/vacancies/{id}/favorite    # Удалить из избранного
```

### Анализ вакансий
```
GET    /api/v2/vacancies/{id}/analyses     # Список анализов вакансии
POST   /api/v2/vacancies/{id}/analyses     # Создать анализ
GET    /api/v2/vacancies/{id}/analyses/types # Типы анализов
```

### Универсальный анализ
```
GET    /api/v2/analyses/{id}          # Получить анализ
DELETE /api/v2/analyses/{id}          # Удалить анализ
```

### Инвайты
```
GET    /api/v2/invites               # Список инвайтов
POST   /api/v2/invites               # Сгенерировать коды
GET    /api/v2/invites/unused        # Неиспользованные коды
GET    /api/v2/invites/{code}        # Информация об инвайте
POST   /api/v2/invites/{code}/use    # Использовать код
DELETE /api/v2/invites/{code}        # Удалить код
```

### Задачи (Celery)
```
POST   /api/v2/tasks/import_vacancies      # Импорт вакансий с hh.ru
GET    /api/v2/tasks/{task_id}           # Статус задачи
POST   /api/v2/tasks/analysis_vacancies   # Анализ вакансий AI
```

### Импорт
```
POST   /api/v2/upload/conversations_import   # Импорт Claude/GPT
```


## 🧪 Тестирование

```bash
# Все тесты
pytest

# С покрытием
pytest --cov=app --cov-report=html

# Только API v2 тесты
pytest tests/api/v2/

# Конкретный файл
pytest tests/api/v2/test_documents.py

```


## 🔨 Разработка

### Качество кода
```bash
# Линтинг
ruff check app/

# Форматирование
ruff format app/

# Проверка типов
mypy app/
```

### Миграции БД
```bash
# Создать миграцию
alembic revision --autogenerate -m "описание"

# Применить
alembic upgrade head

# Откатить
alembic downgrade -1
```

### Docker команды
```bash
make build          # Собрать образы
make up             # Запустить сервисы
make down           # Остановить сервисы
make logs-app       # Логи приложения
make db-shell       # PostgreSQL shell
make health         # Проверить здоровье
```


## 📁 Структура проекта

```
app/
├── api/v2/                    # API v2 (курсорная пагинация)
│   ├── users.py               # Аутентификация
│   ├── conversation.py        # Диалоги
│   ├── message.py             # Сообщения
│   ├── fact.py                # Факты (memory)
│   ├── prompt.py              # Промпты
│   ├── document.py            # Документы
│   ├── vacancy.py             # Вакансии (hh.ru)
│   ├── vacancy_analysis.py    # AI анализ вакансий
│   ├── analysis.py            # Универсальный анализ
│   ├── invite.py              # Инвайты
│   ├── task.py                # Celery задачи
│   └── upload.py              # Импорт диалогов
├── auth/                      # JWT аутентификация
│   ├── auth.py                # Логика авторизации
│   ├── hashing.py             # Хеширование паролей
│   ├── tokens.py              # JWT токены
│   ├── jwt_config.py          # Конфигурация JWT
│   └── dependencies.py        # Auth зависимости
├── configs/                   # Конфигурации
│   ├── llm_config.py          # LLM конфигурация
│   ├── memory.py              # Memory конфигурация
│   ├── celery_config.py       # Celery конфигурация
│   ├── settings.py            # Настройки приложения
│   └── llms/                  # LLM базовые классы
├── database/                  # База данных
│   ├── postgres_db.py         # PostgreSQL настройки
│   └── session.py             # Сессии БД
├── depends/                   # Dependency injection
│   ├── db_depends.py          # БД зависимости
│   ├── llm_depends.py         # LLM зависимости
│   └── mem0_depends.py        # Memory зависимости
├── enum/                      # Enum классы
├── llms/                      # LLM реализации
│   ├── base.py                # Базовый класс LLM
│   └── openai.py              # OpenAI/OpenRouter реализация
├── main.py                    # Главный файл приложения
├── lifespan.py                # Управление жизненным циклом
├── middleware/                # Middleware
│   ├── logging.py             # Логирование
│   ├── security_middleware.py # Security headers
│   └── timing_middleware.py   # Замер времени запросов
├── migrations/                # Alembic миграции
│   ├── env.py                 # Environment
│   └── versions/              # Файлы миграций
├── models/                    # SQLAlchemy модели
│   ├── base_model.py          # Базовая модель
│   ├── users.py               # User
│   ├── conversations.py       # Conversation
│   ├── messages.py            # Message
│   ├── facts.py               # Fact
│   ├── prompts.py             # Prompts
│   ├── invites.py             # Invite
│   ├── vacancies.py           # Vacancy
│   ├── vacancy_analysis.py    # VacancyAnalysis
│   ├── documents.py           # Document
│   └── user_vacancies.py      # User-Vacancy (many-to-many)
├── prompts/                   # Промпты для LLM
│   ├── prompts_base.py        # Базовые промпты
│   ├── prompts_for_parse.py   # Промпты для парсинга
│   └── prompts_for_analysis.py # Промпты для анализа
├── schemas/                   # Pydantic схемы
│   ├── pagination.py          # Схемы пагинации
│   ├── users.py               # User схемы
│   ├── conversations.py       # Conversation схемы
│   ├── messages.py            # Message схемы
│   ├── facts.py               # Fact схемы
│   ├── prompts.py             # Prompts схемы
│   ├── invites.py             # Invite схемы
│   ├── vacancies.py           # Vacancy схемы
│   ├── vacancy_analysis.py    # VacancyAnalysis схемы
│   └── documents.py           # Document схемы
├── services/                  # Бизнес-логика
│   ├── fact_service.py        # Факты сервис
│   └── document_service.py    # Документы сервис
├── tasks/                     # Celery задачи
│   └── vacancy_tasks.py       # Задачи для вакансий
├── tools/                     # Инструменты
│   ├── headhunter/            # hh.ru интеграция
│   ├── invite/                # Инвайты инструменты
│   ├── upload/                # Загрузка файлов
│   └── ai_research/           # AI исследования
└── utils/                     # Утилиты
    ├── utils.py               # Общие утилиты
    ├── utils_for_pagination.py # Утилиты пагинации
    ├── user_validators.py     # Валидаторы пользователей
    ├── db_optimizer.py        # Оптимизатор БД
    ├── claude_history_converter.py  # Claude.ai конвертер
    ├── gpt_history_converter.py     # GPT конвертер
    └── claude_split_conversations_async.py # Разделение диалогов
```


## ⚠️ Важно

Это **учебный pet-проект** для исследования AI-архитектур. Может содержать:
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

## Лицензия

MIT — подробности в файле [LICENSE](LICENSE)
