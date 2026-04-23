from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "jobs.db"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs"


class Settings(BaseSettings):
    db_path: str = str(DEFAULT_DB_PATH)
    output_dir: str = str(DEFAULT_OUTPUT_DIR)
    max_chars_per_chunk: int = 200
    worker_poll_interval_ms: int = 500
    request_timeout_sec: int = 20
    chunk_retry_max: int = 2
    random_delay_min_sec: float = 0.5
    random_delay_max_sec: float = 1.5
    silent_between_chunks_ms: int = 20
    token_ttl_sec: int = 3600
    host: str = "127.0.0.1"
    port: int = 8000
    control_token: str | None = None
    control_shutdown_timeout_sec: float = 10.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
