from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    db_path: str = "./python-tts-backend/data/jobs.db"
    output_dir: str = "./python-tts-backend/outputs"
    max_chars_per_chunk: int = 200
    worker_poll_interval_ms: int = 500
    request_timeout_sec: int = 20
    chunk_retry_max: int = 2
    random_delay_min_sec: float = 0.5
    random_delay_max_sec: float = 1.5
    silent_between_chunks_ms: int = 180
    token_ttl_sec: int = 3600
    host: str = "127.0.0.1"
    port: int = 8000

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
