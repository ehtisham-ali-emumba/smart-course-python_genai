"""Core service configuration."""

from pydantic_settings import BaseSettings


class CoreSettings(BaseSettings):
    """Core service settings."""

    # Kafka settings
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:29092"
    SCHEMA_REGISTRY_URL: str = "http://schema-registry:8081"

    # Legacy settings (keep for compatibility)
    RABBITMQ_URL: str = "amqp://smartcourse:smartcourse_secret@rabbitmq:5672//"
    CELERY_RESULT_BACKEND: str = "redis://:smartcourse_secret@redis:6379/2"

    # Logging
    LOG_LEVEL: str = "INFO"

    # Temporal settings
    TEMPORAL_HOST: str = "temporal:7233"
    TEMPORAL_NAMESPACE: str = "default"
    TEMPORAL_TASK_QUEUE: str = "smartcourse-enrollment"

    # Mock activity settings (for testing/development)
    MOCK_ACTIVITY_DELAY_MIN: float = 5.0  # Minimum simulated delay in seconds (per activity)
    MOCK_ACTIVITY_DELAY_MAX: float = 7.0  # Maximum simulated delay in seconds
    MOCK_ACTIVITY_FAIL_RATE: float = 0.0  # Probability of simulated failure (0.0-1.0)

    # NOTE: Service URLs not needed in mock mode
    # Uncomment when switching to real HTTP activity calls:
    # USER_SERVICE_URL: str = "http://user-service:8001"
    # COURSE_SERVICE_URL: str = "http://course-service:8002"
    # NOTIFICATION_SERVICE_URL: str = "http://notification-service:8005"
    # HTTP_TIMEOUT_SECONDS: float = 30.0

    model_config = {"env_prefix": "", "case_sensitive": True}


core_settings = CoreSettings()
