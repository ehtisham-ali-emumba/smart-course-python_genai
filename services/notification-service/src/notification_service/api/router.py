from fastapi import APIRouter
from notification_service.api.notification import router as notification_router

router = APIRouter()
router.include_router(notification_router, prefix="/notifications", tags=["notifications"])
