"""Core service configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class CoreSettings(BaseSettings):
    """Core service settings."""

    # Kafka settings
    KAFKA_BOOTSTRAP_SERVERS: str
    SCHEMA_REGISTRY_URL: str

    # Legacy settings (keep for compatibility)
    RABBITMQ_URL: str
    CELERY_RESULT_BACKEND: str

    # Logging
    LOG_LEVEL: str

    # Temporal settings
    TEMPORAL_HOST: str
    TEMPORAL_NAMESPACE: str
    TEMPORAL_TASK_QUEUE: str

    # Mock activity settings (for testing/development)
    MOCK_ACTIVITY_DELAY_MIN: float
    MOCK_ACTIVITY_DELAY_MAX: float
    MOCK_ACTIVITY_FAIL_RATE: float

    # NOTE: Service URLs not needed in mock mode
    # Uncomment when switching to real HTTP activity calls:
    # USER_SERVICE_URL: str = "http://user-service:8001"
    # COURSE_SERVICE_URL: str = "http://course-service:8002"
    # NOTIFICATION_SERVICE_URL: str = "http://notification-service:8005"
    # HTTP_TIMEOUT_SECONDS: float = 30.0

    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="", case_sensitive=True
    )


core_settings = CoreSettings()  # type: ignore[call-arg]  # Loaded from .env at runtime
