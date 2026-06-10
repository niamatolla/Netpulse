from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    app_name: str = "NetPulse"
    app_version: str = "0.1.0"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # CORS
    cors_origins: list = ["http://localhost:5173"]

    # Polling
    poll_interval: int = 10
    ping_count: int = 5
    ping_timeout: float = 2.0
    history_limit: int = 100
    poller_enabled: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache()
def get_settings() -> Settings:
    return Settings()