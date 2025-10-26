# YourProject

## Установка

```bash
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
├── tests/            # Тесты
└── pyproject.toml    # Конфигурация инструментов
```
