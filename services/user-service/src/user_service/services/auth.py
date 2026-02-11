from sqlalchemy.ext.asyncio import AsyncSession

from user_service.core.security import get_password_hash, verify_password
from user_service.models.user import User
from user_service.repositories.user import UserRepository
from user_service.schemas.auth import UserRegister


class AuthService:
    """Authentication service for user registration and authentication."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)

    async def register(self, user_data: UserRegister) -> User:
        """
        Register a new user.

        Args:
            user_data: User registration data

        Returns:
            Created user object

        Raises:
            ValueError: If email already exists
        """
        # Check if email already exists
        if await self.user_repo.email_exists(user_data.email):
            raise ValueError(f"Email {user_data.email} is already registered")

        # Hash password
        password_hash = get_password_hash(user_data.password)

        # Create user
        user = await self.user_repo.create({
            "email": user_data.email,
            "first_name": user_data.first_name,
            "last_name": user_data.last_name,
            "password_hash": password_hash,
            "role": user_data.role,
            "is_active": True,
            "is_verified": False,
        })

        return user

    async def authenticate(self, email: str, password: str) -> User | None:
        """
        Authenticate a user by email and password.

        Args:
            email: User email
            password: Plain password

        Returns:
            User object if authentication successful, None otherwise
        """
        user = await self.user_repo.get_by_email(email)

        if not user or not user.is_active:
            return None

        if not verify_password(password, user.password_hash):
            return None

        return user

    async def get_user_by_id(self, user_id: int) -> User | None:
        """Get user by ID."""
        return await self.user_repo.get_by_id(user_id)
