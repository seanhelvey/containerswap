from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

# Module-level so tests can derive their own database name from it without
# duplicating the literal and letting the two drift apart.
DEFAULT_DATABASE_URL = "postgresql+psycopg://containerswap:localdev@localhost:5433/containerswap"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CS_", extra="ignore")

    site_name: str = "SecondhandPlastic.com"
    # Deliberately a recognisable placeholder, not a real key. main.py logs an
    # error at startup if it survives into production.
    secret_key: str = "dev-only-insecure-change-me"  # noqa: S105
    debug: bool = False

    # Postgres, both locally (docker compose up -d) and in production (Supabase).
    # In production this must be the *transaction pooler* (port 6543): zero-downtime
    # deploys run old and new instances at once, and the direct connection's limit is
    # far too low for that.
    database_url: str = DEFAULT_DATABASE_URL
    # Alembic runs DDL, which is unreliable through the transaction pooler. Point this
    # at the *direct* connection (port 5432). Empty == same as database_url, which is
    # what local dev wants since there is no pooler in front of the container.
    migration_database_url: str = ""

    @field_validator("database_url", "migration_database_url")
    @classmethod
    def _force_psycopg3(cls, value: str) -> str:
        """Pin the driver to psycopg 3, whatever scheme was pasted in.

        Supabase hands out `postgresql://`, and on that bare scheme SQLAlchemy
        reaches for psycopg2 — which is not installed, so the app dies at import
        with ModuleNotFoundError. Correcting it here rather than trusting every
        dashboard field and .env to carry the `+psycopg` suffix.
        """
        for prefix in ("postgresql://", "postgres://", "postgresql+psycopg2://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix) :]
        return value

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

    # Transactional email (Resend). Unset means no mail is sent at all, which is what
    # local development wants — no configuration, and no risk of mailing real people
    # from a dev box. Without it nobody learns they have a message, so production
    # needs it: it is the only thing that brings a seller back to their inbox.
    resend_api_key: str = ""
    # Must be on a domain verified with Resend, or every send is rejected.
    email_from: str = ""
    # Where abuse reports go. Unset means reports are logged and nothing else.
    # Beta feedback (app/email.py:notify_new_feedback) reuses this too — one
    # operator, one inbox, until there's a reason to split them.
    report_email: str = ""
    # Absolute base for links in emails; relative URLs are useless in a mail client.
    site_url: str = "http://127.0.0.1:8000"

    @field_validator("supabase_url", "site_url")
    @classmethod
    def _normalise_supabase_url(cls, value: str) -> str:
        """Accept a bare host, and never keep a trailing slash.

        The dashboard shows this value without a scheme, so it gets pasted in that
        way; httpx then rejects the upload URL outright. Both halves of the fix are
        here because storage.py and the CSP both build strings from this and each
        would otherwise need its own guard.
        """
        value = value.strip().rstrip("/")
        if value and not value.startswith(("http://", "https://")):
            value = f"https://{value}"
        return value

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
    def email_enabled(self) -> bool:
        return bool(self.resend_api_key and self.email_from)

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
