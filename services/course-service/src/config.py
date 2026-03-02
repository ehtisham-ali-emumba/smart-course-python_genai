from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # PostgreSQL
    DATABASE_URL: str

    # MongoDB
    MONGODB_URL: str
    MONGODB_DB_NAME: str

    # Redis
    REDIS_URL: str

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str
    SCHEMA_REGISTRY_URL: str

    # ── S3 File Upload ────────────────────────────────
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str
    S3_BUCKET_NAME: str
    S3_PRESIGNED_URL_EXPIRY: int = 3600
    S3_MAX_FILE_SIZE_MB: float = 500.0

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


settings = Settings()  # type: ignore[call-arg]  # Loaded from .env at runtime
