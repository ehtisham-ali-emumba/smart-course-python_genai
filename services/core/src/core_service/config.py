from pydantic_settings import BaseSettings


class CoreSettings(BaseSettings):
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:29092"
    RABBITMQ_URL: str = "amqp://smartcourse:smartcourse_secret@rabbitmq:5672//"
    CELERY_RESULT_BACKEND: str = "redis://:smartcourse_secret@redis:6379/2"
    SCHEMA_REGISTRY_URL: str = "http://schema-registry:8081"
    LOG_LEVEL: str = "INFO"
    TEMPORAL_HOST: str = "temporal:7233"
    TEMPORAL_NAMESPACE: str = "smartcourse"
    TEMPORAL_TASK_QUEUE: str = "smartcourse-core"

    model_config = {"env_prefix": "", "case_sensitive": True}


core_settings = CoreSettings()
