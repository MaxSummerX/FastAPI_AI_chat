from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import conversation, fact, prompts, tools, upload, users
from app.api.v2 import analysis as analysis_v2
from app.api.v2 import conversation as conversation_v2
from app.api.v2 import fact as fact_v2
from app.api.v2 import invite as invite_v2
from app.api.v2 import prompt as prompt_v2
from app.api.v2 import upload as upload_v2
from app.api.v2 import users as users_v2
from app.api.v2 import vacancy as vacancy_v2
from app.configs.settings import settings
from app.middleware.logging import log_middleware
from app.middleware.security_middleware import add_security_headers
from app.middleware.timing_middleware import TimingMiddleware


# Создаём приложение FastAPI
app = FastAPI(title="AI chat", version="0.1.1")

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

# Подключаем маршруты категорий
app.include_router(users.router_v1, prefix="/api/v1")
app.include_router(conversation.router_v1, prefix="/api/v1")
app.include_router(fact.router_v1, prefix="/api/v1")
app.include_router(prompts.router_v1, prefix="/api/v1")
app.include_router(upload.router_v1, prefix="/api/v1")
app.include_router(tools.router_V1, prefix="/api/v1")

# Подключаем маршруты категорий 2ой версии
app.include_router(upload_v2.router, prefix="/api/v2")
app.include_router(users_v2.router, prefix="/api/v2")
app.include_router(conversation_v2.router, prefix="/api/v2")
app.include_router(fact_v2.router, prefix="/api/v2")
app.include_router(prompt_v2.router, prefix="/api/v2")
app.include_router(vacancy_v2.router, prefix="/api/v2")
app.include_router(invite_v2.router, prefix="/api/v2")
app.include_router(analysis_v2.router, prefix="/api/v2")
