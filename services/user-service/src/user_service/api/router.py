from fastapi import APIRouter
from user_service.api import auth, profile

# Main API router
router = APIRouter()

# Include authentication endpoints under /api/auth
router.include_router(auth.router, prefix="/auth", tags=["Authentication"])

# Include profile endpoints under /api/profile
router.include_router(profile.router, prefix="/profile", tags=["Profile"])
