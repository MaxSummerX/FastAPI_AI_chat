from fastapi import FastAPI

from app.api.v1 import convertion, users
from app.utils import polygon


# Создаём приложение FastAPI
app = FastAPI(title="AI chat", version="0.1.0")


# Подключаем маршруты категорий
app.include_router(users.router_v1)
app.include_router(convertion.router_v1)

# тестовые маршруты
app.include_router(polygon.polygon_func)
