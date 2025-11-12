from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import conversation, fact, users
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
app.include_router(users.router_v1, prefix="/api/v1")
app.include_router(fact.router_v1, prefix="/api/v1")
app.include_router(conversation.router_v1, prefix="/api/v1")


# Главная страница
@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


# Статические ресурсы
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
