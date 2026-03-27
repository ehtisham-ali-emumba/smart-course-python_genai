"""AI Service configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """AI Service settings loaded from environment variables."""

    # MongoDB (read-only access to course content)
    MONGODB_URL: str
    MONGODB_DB_NAME: str

    # Redis (caching)
    REDIS_URL: str

    # Kafka (event publishing)
    KAFKA_BOOTSTRAP_SERVERS: str
    SCHEMA_REGISTRY_URL: str

    # Course Service (internal HTTP calls)
    COURSE_SERVICE_URL: str = "http://course-service:8002"

    # LLM Provider (future use)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    # Qdrant (future use)
    QDRANT_URL: str = "http://qdrant:6333"
    QDRANT_COLLECTION: str = "course_embeddings"

    # S3 (private audio/PDF download — same bucket as course-service)
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "ap-southeast-2"
    S3_BUCKET_NAME: str = "smartcourse-uploads-bucket"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")


settings = Settings()  # type: ignore[call-arg]
