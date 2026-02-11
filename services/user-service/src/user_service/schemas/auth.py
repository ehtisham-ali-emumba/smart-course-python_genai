from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    """User registration request schema."""
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8, max_length=100)
    role: str = Field(default="student", pattern="^(student|instructor)$")


class UserLogin(BaseModel):
    """User login request schema."""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """JWT token response schema."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    """Refresh token request schema."""
    refresh_token: str
