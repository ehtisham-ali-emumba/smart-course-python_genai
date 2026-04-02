from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    KAFKA_BOOTSTRAP_SERVERS: str
    SCHEMA_REGISTRY_URL: str

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")


settings = Settings()  # type: ignore[call-arg]
