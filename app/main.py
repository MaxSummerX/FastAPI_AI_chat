from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.infrastructure.settings.settings import settings
from app.lifespan import lifespan
from app.presentation.middleware.logging import log_middleware
from app.presentation.middleware.security_middleware import add_security_headers
from app.presentation.middleware.timing_middleware import TimingMiddleware
from app.presentation.routers import admin, v1
from app.presentation.routers.v2 import analysis, conversation, document, fact, prompt, task, upload, vacancy


app = FastAPI(
    title="AI chat",
    version="0.2.1",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,  # False для JWT аутентификации
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)
app.add_middleware(TimingMiddleware)  # Замер времени
app.middleware("http")(log_middleware)
app.middleware("http")(add_security_headers)  # Security headers


app.include_router(v1.api_v1)
# Подключаем маршруты 2ой версии
app.include_router(upload.router, prefix="/api/v2")
app.include_router(conversation.router, prefix="/api/v2")
app.include_router(fact.router, prefix="/api/v2")
app.include_router(prompt.router, prefix="/api/v2")
app.include_router(vacancy.router, prefix="/api/v2")
app.include_router(analysis.router, prefix="/api/v2")
app.include_router(task.router, prefix="/api/v2")
app.include_router(document.router, prefix="/api/v2")
# Admin routes
app.include_router(admin.router)


@app.get("/health", tags=["Health Check"])
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}
