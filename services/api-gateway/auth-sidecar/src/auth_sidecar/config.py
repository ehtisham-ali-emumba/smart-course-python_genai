from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Auth sidecar settings — loaded from environment variables."""

    JWT_SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
