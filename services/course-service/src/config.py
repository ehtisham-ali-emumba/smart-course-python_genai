from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # PostgreSQL
    DATABASE_URL: str = "postgresql://smartcourse:smartcourse_secret@localhost:5432/smartcourse"

    # MongoDB
    MONGODB_URL: str = "mongodb://smartcourse:smartcourse_secret@localhost:27017/smartcourse?authSource=admin"
    MONGODB_DB_NAME: str = "smartcourse"

    # Redis
    REDIS_URL: str = "redis://:smartcourse_secret@localhost:6379/1"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
