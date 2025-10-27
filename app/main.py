from fastapi import FastAPI

from app.api.v1 import users


# Создаём приложение FastAPI
app = FastAPI(title="AI chat", version="0.1.0")


# Подключаем маршруты категорий
app.include_router(users.router_v1)
