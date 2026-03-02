from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Notification service configuration."""

    SERVICE_NAME: str
    SERVICE_PORT: int
    LOG_LEVEL: str

    # Future: Email configuration (not used yet)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "no-reply@smartcourse.com"

    # Future: Push notification configuration (not used yet)
    FIREBASE_PROJECT_ID: str = ""

    # Kafka — fire-and-forget event consumption for notifications & certificates
    KAFKA_BOOTSTRAP_SERVERS: str
    RABBITMQ_URL: str
    CELERY_RESULT_BACKEND: str

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


settings = Settings()  # type: ignore[call-arg]  # Loaded from .env at runtime
