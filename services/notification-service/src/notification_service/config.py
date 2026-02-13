from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Notification service configuration."""

    SERVICE_NAME: str = "notification-service"
    SERVICE_PORT: int = 8005
    LOG_LEVEL: str = "INFO"

    # Future: Email configuration (not used yet)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "no-reply@smartcourse.com"

    # Future: Push notification configuration (not used yet)
    FIREBASE_PROJECT_ID: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
