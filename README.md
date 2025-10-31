# FastAPI_AI_chat


## Установка

```bash
# Установка dev окружения
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pre-commit install
```
## Разработка

```bash
# Форматирование и линтинг одной командой
ruff check --fix app tests
ruff format app tests

# Запуск тестов
pytest
```
## Структура проекта

```bash
.
├── app/              # Основной код приложения
│     ├── api/
│     │    └── v1/
│     ├── auth/
│     ├── configs/
│     ├── database/
│     ├── depends/
│     ├── llms/
│     ├── migration/
│     ├── models/
│     ├── schemas/
│     ├── utils/
│     ├── init.py
│     └── main.py
├── tests/            # Тесты
│     └── init.py
├── .gitignore
├── .pre-commit-config.yaml
├── alembic.ini # Настройки alembic
├── env.example
├── pyproject.toml    # Конфигурация инструментов
├── README.md
├── requirements-dev.txt # Dev зависимости
├── start_project.sh # Скрипт инициализации Python проекта с линтерами и форматерами
└── uv.lock

```
*Команда генерации ключ для JWT*
```bash
openssl rand -hex 32
```
