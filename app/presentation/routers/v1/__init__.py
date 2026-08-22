from fastapi import APIRouter

from app.presentation.routers.v1 import analysis, conversation, document, fact, prompt, task, upload, users, vacancy


api_v1 = APIRouter(prefix="/api/v1")

api_v1.include_router(users.router)
api_v1.include_router(document.router)
api_v1.include_router(conversation.router)  # включает message.router
api_v1.include_router(fact.router)
api_v1.include_router(prompt.router)
api_v1.include_router(upload.router)
api_v1.include_router(vacancy.router)  # включает vacancy_analysis.router
api_v1.include_router(analysis.router)
api_v1.include_router(task.router)
