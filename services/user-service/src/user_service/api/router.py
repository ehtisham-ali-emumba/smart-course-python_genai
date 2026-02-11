from fastapi import APIRouter
from user_service.api import auth, profile

# Main API router
router = APIRouter()

# Include authentication endpoints under /auth
router.include_router(auth.router, prefix="/auth")

# Include profile endpoints under /profile
router.include_router(profile.router, prefix="/profile")
