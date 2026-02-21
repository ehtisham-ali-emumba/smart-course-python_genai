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

    # Kafka — fire-and-forget event consumption for notifications & certificates
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:29092"
    RABBITMQ_URL: str = "amqp://smartcourse:smartcourse_secret@rabbitmq:5672//"
    CELERY_RESULT_BACKEND: str = "redis://:smartcourse_secret@redis:6379/2"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
