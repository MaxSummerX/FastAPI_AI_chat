from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import convertion, users
from app.api.v2 import convertion_v2


# Статические файлы
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

# Создаём приложение FastAPI
app = FastAPI(title="AI chat", version="0.1.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене укажи конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем маршруты категорий
app.include_router(users.router_v1)
app.include_router(convertion.router_v1)
app.include_router(convertion_v2.router_v2)

# Монтируем статики
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
