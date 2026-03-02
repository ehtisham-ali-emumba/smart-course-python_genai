from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Auth sidecar settings — loaded from environment variables."""

    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


settings = Settings()  # type: ignore[call-arg]  # Loaded from .env at runtime
