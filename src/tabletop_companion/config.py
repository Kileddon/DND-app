from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TTC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///data/tabletop_companion.sqlite3"
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = "INFO"
    host_secret_path: Path = Path("data/host-secret.key")
    frontend_dist: Path = Path("frontend/dist")
    media_library: Path = Path("data/media")
    websocket_room_limit: int = Field(default=60, ge=1, le=500)
    websocket_device_limit: int = Field(default=3, ge=1, le=20)
    websocket_queue_size: int = Field(default=128, ge=8, le=4096)
