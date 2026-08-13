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

    # Postgres, both locally (docker compose up -d) and in production (Supabase).
    # In production this must be the *transaction pooler* (port 6543): zero-downtime
    # deploys run old and new instances at once, and the direct connection's limit is
    # far too low for that.
    database_url: str = "postgresql+psycopg://containerswap:localdev@localhost:5433/containerswap"
    # Alembic runs DDL, which is unreliable through the transaction pooler. Point this
    # at the *direct* connection (port 5432). Empty == same as database_url, which is
    # what local dev wants since there is no pooler in front of the container.
    migration_database_url: str = ""

    # Local scratch space: uploads when no object store is configured, and nothing
    # else. There is no persistent volume in production, so anything written here is
    # gone on the next redeploy.
    data_dir: Path = BASE_DIR / "data"

    # Object storage. Unset == write uploads to data_dir, which is the local dev path.
    # Set all three in production; the service key is server-side only and must never
    # reach a template or a log line.
    supabase_url: str = ""
    supabase_service_key: str = ""
    storage_bucket: str = "listing-photos"

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
    def uses_object_storage(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key and self.storage_bucket)

    @property
    def storage_public_base(self) -> str:
        """Public read URL for the bucket, without a trailing slash.

        The bucket is public on purpose: the home page, the map and
        /api/listings.geojson all serve listing photos to anonymous visitors, so
        signed URLs would buy no privacy and cost caching. Photos are safe to expose
        because images.process_upload strips EXIF, and filenames carry 128 bits of
        entropy so they cannot be enumerated.
        """
        return f"{self.supabase_url.rstrip('/')}/storage/v1/object/public/{self.storage_bucket}"

    @property
    def alembic_url(self) -> str:
        return self.migration_database_url or self.database_url

    @property
    def secret_is_default(self) -> bool:
        return self.secret_key == "dev-only-insecure-change-me"  # noqa: S105


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
