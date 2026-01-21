from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.depends.db_depends import get_async_postgres_db
from app.models.users import User as UserModel
from app.tools.ai_research.ai_scan import analyze_vacancy_from_db


router = APIRouter(prefix="/head_hunter", tags=["AI_analysis_V2"])


DEFAULT_PER_PAGE = 20
MINIMUM_PER_PAGE = 1
MAXIMUM_PER_PAGE = 100


@router.get("/ai_analysis", status_code=status.HTTP_200_OK)
async def ai_analysis(
    id_vacancy: UUID,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_postgres_db),
) -> str | dict[str, Any] | None:
    return await analyze_vacancy_from_db(vacancy_id=id_vacancy, user_id=current_user.id, session=db)
