from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True)
class Settings:
    freesound_api_key: str | None
    database_path: Path
    frontend_dir: Path
    preview_cache_dir: Path
    freesound_base_url: str = "https://freesound.org"
    openverse_client_id: str | None = None
    openverse_client_secret: str | None = None
    openverse_base_url: str = "https://api.openverse.org/v1"
    jamendo_client_id: str | None = None
    jamendo_base_url: str = "https://api.jamendo.com/v3.0"


def get_settings() -> Settings:
    dotenv = _read_dotenv(PROJECT_ROOT / ".env")

    def env_value(name: str, default: str | None = None) -> str | None:
        return os.environ.get(name) or dotenv.get(name) or default

    db_path = Path(env_value("SOUNDSCRAPPER_DB_PATH", "sound_scout.db") or "sound_scout.db")
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_path

    frontend_dir = Path(env_value("SOUNDSCRAPPER_FRONTEND_DIR", "frontend") or "frontend")
    if not frontend_dir.is_absolute():
        frontend_dir = PROJECT_ROOT / frontend_dir

    preview_cache_dir = Path(
        env_value("SOUNDSCRAPPER_PREVIEW_CACHE_DIR", ".cache/previews") or ".cache/previews"
    )
    if not preview_cache_dir.is_absolute():
        preview_cache_dir = PROJECT_ROOT / preview_cache_dir

    api_key = env_value("FREESOUND_API_KEY")

    return Settings(
        freesound_api_key=api_key if api_key else None,
        database_path=db_path,
        frontend_dir=frontend_dir,
        preview_cache_dir=preview_cache_dir,
        freesound_base_url=env_value("FREESOUND_BASE_URL", "https://freesound.org")
        or "https://freesound.org",
        openverse_client_id=env_value("OPENVERSE_CLIENT_ID"),
        openverse_client_secret=env_value("OPENVERSE_CLIENT_SECRET"),
        openverse_base_url=env_value("OPENVERSE_BASE_URL", "https://api.openverse.org/v1")
        or "https://api.openverse.org/v1",
        jamendo_client_id=env_value("JAMENDO_CLIENT_ID"),
        jamendo_base_url=env_value("JAMENDO_BASE_URL", "https://api.jamendo.com/v3.0")
        or "https://api.jamendo.com/v3.0",
    )
