from fastapi import APIRouter
from user_service.api import auth

router = APIRouter(prefix="/auth")
router.include_router(auth.router)
