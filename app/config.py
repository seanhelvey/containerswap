from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CS_", extra="ignore")

    site_name: str = "ContainerSwap"
    # Deliberately a recognisable placeholder, not a real key. main.py logs an
    # error at startup if it survives into production.
    secret_key: str = "dev-only-insecure-change-me"  # noqa: S105
    debug: bool = False

    # Runtime data. Must point at a persistent volume in production or uploads and
    # the database are lost on every redeploy.
    data_dir: Path = BASE_DIR / "data"

    # Local flavour without forking the code. Empty string == global framing.
    home_region: str = ""

    # Map default view when the visitor has not granted geolocation.
    default_lat: float = 40.8021
    default_lng: float = -124.1637
    default_zoom: int = 9

    # Uploads
    max_upload_bytes: int = 8 * 1024 * 1024
    target_image_bytes: int = 300 * 1024
    max_image_px: int = 1280

    # Privacy: listing coordinates are jittered by up to this many metres before
    # they are stored, so a pin never marks someone's front door.
    location_fuzz_m: int = 400

    session_max_age_s: int = 60 * 60 * 24 * 30

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "containerswap.db"

    @property
    def secret_is_default(self) -> bool:
        return self.secret_key == "dev-only-insecure-change-me"  # noqa: S105


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
