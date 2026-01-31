# Используем Python версии из твоего стека
FROM python:3.13-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Создаём пользователя СРАЗУ с home директорией
RUN groupadd -r appuser && \
    useradd -r -g appuser -m -d /home/appuser appuser && \
    mkdir -p /home/appuser/.cache/uv && \
    chown -R appuser:appuser /home/appuser

# Устанавливаем uv глобально
RUN pip install --no-cache-dir uv

# Копируем ТОЛЬКО файлы зависимостей для кеширования
COPY pyproject.toml.prod ./pyproject.toml
COPY uv.lock ./

# Устанавливаем зависимости (этот слой кешируется)
RUN uv sync --frozen --no-dev --no-install-project

# Копируем код приложения (инвалидируется чаще)
COPY app ./app
COPY alembic.ini ./

# Меняем владельца файлов
RUN chown -R appuser:appuser /app

# Переключаемся на non-root пользователя
USER appuser

# Открываем порт
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Production переменные окружения
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Запускаем с production настройками
CMD ["uv", "run", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--log-level", "info"]
