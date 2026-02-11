from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def get_profile():
    return {"message": "Mock user profile endpoint"}
