from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "AI-HR"
    APP_ADDRESS: str = "0.0.0.0"
    APP_PORT: int = 8000

    MISTRAL_API_KEY: str
    MISTRAL_MODEL: str = "mistral-large-latest"

    LOG_DIR: str = "logs"
    MAX_VALIDATION_ATTEMPTS: int = 3

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[2] / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


settings = Settings()
