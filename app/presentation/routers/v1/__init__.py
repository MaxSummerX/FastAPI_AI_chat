from fastapi import APIRouter

from app.presentation.routers.v1 import users


api_v1 = APIRouter(prefix="/api/v1")

api_v1.include_router(users.router)
