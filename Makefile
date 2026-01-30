.PHONY: help build rebuild rebuild-app up down restart logs ps clean clean-all prune fix-perms backup restore

# ============================================================================
# Makefile для управления AI_chat
# ============================================================================

help: ## Показать эту справку
	@echo "Доступные команды:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ============================================================================
# Production (порты открыты для разработки)
# ============================================================================

build: ## Собрать Docker образы
	docker compose -f docker-compose.prod.yml build

rebuild: ## Собрать и пересоздать ВСЕ контейнеры (включая БД - данные сохраняются)
	docker compose -f docker-compose.prod.yml up -d --build --force-recreate

rebuild-app: ## Собрать и пересоздать ТОЛЬКО app + celery_worker (РЕКОМЕНДУЕТСЯ)
	docker compose -f docker-compose.prod.yml up -d --build --force-recreate app celery_worker

up: ## Запустить все сервисы
	docker compose -f docker-compose.prod.yml up -d

down: ## Остановить и удалить контейнеры
	docker compose -f docker-compose.prod.yml down

restart: ## Перезапустить все сервисы
	docker compose -f docker-compose.prod.yml restart

deploy: ## Обновить с GitHub и пересоздать app + celery
	git pull
	docker compose -f docker-compose.prod.yml up -d --build --force-recreate app celery_worker

logs: ## Посмотреть логи всех сервисов
	docker compose -f docker-compose.prod.yml logs -f

logs-app: ## Посмотреть логи только приложения
	docker compose -f docker-compose.prod.yml logs -f app

ps: ## Показать статус сервисов
	docker compose -f docker-compose.prod.yml ps

clean: ## Удалить контейнеры, сети (сохранив volumes)
	docker compose -f docker-compose.prod.yml down

clean-all: ## Удалить ВСЁ включая volumes (ОПАСНО!)
	docker compose -f docker-compose.prod.yml down -v

prune: ## Удалить остановленные контейнеры и образы <none>
	docker container prune -f
	docker image prune -f

# ============================================================================
# Разработка (локально)
# ============================================================================

dev-build: ## Собрать только app контейнер для разработки
	docker build -t ai-chat .

dev-run: ## Запустить app с подключением к сервисам на сервере
	docker run --rm --name ai-chat-app --network host --env-file .env ai-chat

# ============================================================================
# Бэкапы
# ============================================================================

backup: ## Бэкап всех данных
	@echo "Создание бэкапа..."
	@mkdir -p ./backups
	@tar -czf ./backups/ai-chat-$(shell date +%Y%m%d-%H%M%S).tar.gz ./storage/
	@echo "Бэкап создан: ./backups/ai-chat-$(shell date +%Y%m%d-%H%M%S).tar.gz"

restore: ## Восстановить из бэкапа (использование: make restore BACKUP=file.tar.gz)
	@if [ -z "$(BACKUP)" ]; then echo "Укажите файл бэкапа: make restore BACKUP=./backups/file.tar.gz"; exit 1; fi
	@echo "Восстановление из $(BACKUP)..."
	@tar -xzf $(BACKUP)
	@echo "Восстановление завершено"

# ============================================================================
# Утилиты
# ============================================================================

init-ollama: ## Инициализировать модели Ollama
	docker exec AI_chat_ollama ollama pull nomic-embed-text:latest

db-migrate: ## Запустить миграции БД (через docker)
	docker exec AI_chat_app uv run alembic upgrade head

db-shell: ## Открыть PostgreSQL shell
	docker exec -it AI_chat_postgres psql -U postgres -d ai_chat_db

redis-shell: ## Открыть Redis shell
	docker exec -it AI_chat_redis redis-cli -a $$REDIS_PASSWORD

# ============================================================================
# Мониторинг
# ============================================================================

stats: ## Статистика ресурсов контейнеров
	docker stats --no-stream

health: ## Проверить здоровье сервисов
	@echo "=== PostgreSQL ==="
	@docker exec AI_chat_postgres pg_isready -U postgres || echo "❌ PostgreSQL не готов"
	@echo "\n=== Redis ==="
	@docker exec AI_chat_redis redis-cli -a $$REDIS_PASSWORD ping || echo "❌ Redis не готов"
	@echo "\n=== Qdrant ==="
	@curl -s http://localhost:6333/health || echo "❌ Qdrant не готов"
	@echo "\n=== Neo4j ==="
	@curl -s http://localhost:7474 || echo "❌ Neo4j не готов"
	@echo "\n=== Ollama ==="
	@curl -s http://localhost:11434/api/tags > /dev/null && echo "✅ Ollama готов" || echo "❌ Ollama не готов"
	@echo "\n=== App ==="
	@curl -s http://localhost:8000/health || echo "❌ App не готов"
