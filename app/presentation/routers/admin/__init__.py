from fastapi import APIRouter, Depends

from app.presentation.dependencies import get_current_admin_user
from app.presentation.routers.admin import experiment, invite, role, statistics


router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(get_current_admin_user)])

router.include_router(invite.router)
router.include_router(statistics.router)
router.include_router(role.router)
router.include_router(experiment.router)
