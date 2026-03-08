from functools import lru_cache

from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "postgresql://vtchive:vtchive@db:5432/vtchive"
    HOLODEX_TOKEN: str = ""
    TIMEZONE: str = "Asia/Taipei"
    MONITOR_INTERVAL: int = 300
    MAX_CONCURRENT_DOWNLOADS: int = 3
    SCHEDULE_WINDOW_BEFORE_DAYS: int = 1
    SCHEDULE_WINDOW_AFTER_HOURS: int = 12


@lru_cache
def get_settings() -> Settings:
    return Settings()
