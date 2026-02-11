from fastapi import APIRouter, status

router = APIRouter()

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register():
    """Mock register endpoint"""
    return {"message": "User registered (mock)"}

@router.post("/login")
def login():
    """Mock login endpoint"""
    return {"access_token": "mock_token", "refresh_token": "mock_refresh", "token_type": "bearer"}

@router.post("/refresh")
def refresh():
    """Mock refresh endpoint"""
    return {"access_token": "mock_token", "refresh_token": "mock_refresh", "token_type": "bearer"}

@router.get("/me")
def get_current_user():
    """Mock get current user endpoint"""
    return {"id": 1, "email": "mock@example.com", "role": "student"}
