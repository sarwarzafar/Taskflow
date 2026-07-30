"""
Centralized configuration. Every setting is read from the environment,
with sane local defaults — so the same code runs unchanged locally,
in Docker Compose, and (with different env vars) in production.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Redis acts as both the Celery message broker AND the result backend.
    # In Docker Compose this becomes redis://redis:6379/0 (service name as host).
    redis_url: str = "redis://localhost:6379/0"

    # Where processed files live. In Docker this is a shared volume
    # mounted into both the web and worker containers.
    storage_dir: str = "app/storage"
    upload_dir: str = "app/storage/uploads"
    processed_dir: str = "app/storage/processed"
    reports_dir: str = "app/storage/reports"
    logs_dir: str = "app/storage/logs"

    # Celery tuning
    task_max_retries: int = 3
    task_retry_backoff: int = 2  # seconds, doubles each retry

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
