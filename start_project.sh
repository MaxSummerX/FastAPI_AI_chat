#! /bin/bash

# Скрипт инициализации Python проекта с линтерами и форматерами
set -e # Остановка при первой ошибке

# Цвета для вывода
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

log_info() {
	echo -e "${GREEN}✓${NC} $1"
}

log_step() {
	echo -e "${BLUE}→${NC} $1"
}

log_error() {
	echo -e "${RED}✗${NC} $1"
}

# 1. Копирование .gitignore и инициализаци
log_step "Создание .gitignore"
if [ -f "$HOME/.gitignore_global" ]; then
  cp "$HOME/.gitignore_global" .gitignore
  log_info ".gitignore создан из глобального шаблона"
else
  log_step "⚠️  $HOME/.gitignore_global не найден"
  log_step "Создание базового .gitignore..."
	cat > .gitignore << "EOF"
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
.venv/
env/
ENV/

# IDE
.vscode/
.idea/
*.swp
*.swo

# Testing
.pytest_cache/
.coverage
htmlcov/

# Secrets
.env
*.pem
*.key
EOF
  log_info "Создан базовый .gitignore"
fi


#
log_step "Инициализация git репозитория..."
git init

# Установка современной ветки по умолчанию
git config init.defaultBranch main

# Проверка глобальной конфигурации пользователя
if ! git config user.name > /dev/null 2>&1; then
  log_error "Git user.name не настроен. Настройте через: git config --global user.name 'Your Name'"
  exit 1
fi

if ! git config user.email > /dev/null 2>&1; then
  log_error "Git user.email не настроен. Настройте через: git config --global user.email 'email@example.com'"
  exit 1
fi

log_info "Git репозиторий инициализирован"


# 2. Активация виртуального окружения
log_step "Активация виртуального окружения..."
if [ ! -d ".venv" ]; then
	log_error "Виртуальное окружение .venv не найдено. Создать? (y/n)"
	read -r response
	if [ "$response" = "y" ]; then
		python3 -m venv .venv
		log_info "Виртуальное окружение создано"
	else
		log_error "Прерывание установки"
        	exit 1
        fi
fi

source .venv/bin/activate
log_info "Виртуальное окружение активировано"

# 3. Установка зависимостей
log_step "Установка зависимостей для линтеров и форматеров..."
pip install --upgrade pip > /dev/null 2>&1
pip install ruff pre-commit mypy pytest pytest-asyncio > /dev/null 2>&1
log_info "Зависимости установлены"

# 4. Создание структуры проекта
log_step "Создание базовой структуры проекта..."
mkdir -p app tests
touch app/__init__.py
touch tests/__init__.py

# 5. Создание конфигурации Ruff
log_step "Создание конфигурации Ruff..."
cat > pyproject.toml << 'EOF'
[build-system]
requires = ["wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "my-project"
version = "0.1.0"
description = "your_description"
authors = [{ name = "your_name", email = "your_email@example.com" }]
readme = "README.md"
requires-python = ">=3.13"
dependencies = []

[tool.ruff]
line-length = 120
target-version = "py313"
exclude = ["venv", ".venv", "alembic", "docker", ".git", "__pycache__", "app/migrations/env.py"]

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort
    "B",    # flake8-bugbear
    "C4",   # flake8-comprehensions
    "UP",   # pyupgrade
    "ASYNC",# asyncio
]
ignore = ["E203", "E266", "E501", "B008"]

[tool.ruff.lint.isort]
force-single-line = false
force-sort-within-sections = false
lines-after-imports = 2

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

[tool.mypy]
python_version = "3.13"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
exclude = [
    '\.venv',
    'venv',
    '__pycache__',
    'alembic',
]
EOF

log_info "pyproject.toml создан"

# 7. Создание конфигурации pre-commit

log_step "Создание конфигурации pre-commit..."
cat > .pre-commit-config.yaml << 'EOF'
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-merge-conflict

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.13.3
    hooks:
      - id: ruff-check
        args: [ --fix ]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.13.0
    hooks:
      - id: mypy
        args: [--ignore-missing-imports]
EOF

log_info ".pre-commit-config.yaml создан"

# 8. Установка pre-commit hooks

log_step "Установка pre-commit hooks..."
pre-commit install > /dev/null 2>&1
log_info "Pre-commit hooks установлены"

# 9. Создание requirements-dev.txt
log_step "Создание requirements-dev..."
cat > requirements-dev.txt << 'EOF'
ruff==0.13.3
mypy==1.13.0
pre_commit==4.3.0
pytest==8.4.2
pytest-asyncio==1.2.0
EOF

log_info "requirements-dev.txt создан"


# 10. Создание README
log_step "Создание README.md..."
cat > README.md << 'EOF'
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
EOF

log_info "README.md создан"

# 11  Добавление всех файлов и создание первого коммита
git add .
git commit -m "🎉 Initial commit: project structure with linters and formatters

- Added pyproject.toml with ruff, mypy configuration
- Added pre-commit hooks setup
- Added requirements-dev.txt with development dependencies
- Created basic project structure (app/, tests/)
- Added comprehensive .gitignore"

log_info "Git репозиторий инициализирован с первым коммитом"

log_step "Завершение настройки проекта..."
log_info "🚀 Проект успешно инициализирован!"
log_info "Активируйте виртуальное окружение: source .venv/bin/activate"
