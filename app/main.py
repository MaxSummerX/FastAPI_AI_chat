from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import convertion, fact, users
from app.middleware.logging import log_middleware
from app.middleware.timing_middleware import TimingMiddleware


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
app.add_middleware(TimingMiddleware)  # Замер времени
app.middleware("http")(log_middleware)

# Подключаем маршруты категорий
app.include_router(users.router_v1)
app.include_router(fact.router_v1)
app.include_router(convertion.router_v1)

# Монтируем статики
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
