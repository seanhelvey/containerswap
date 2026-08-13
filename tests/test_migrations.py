"""The migrations and the models must describe the same schema.

Nothing else enforces this. The app no longer creates tables at startup, so a model
change that nobody wrote a migration for now fails in production rather than being
quietly patched up on boot — this test is what catches it on the way in instead.
"""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

from app.config import BASE_DIR, settings
from app.db import Base

SCRATCH_DB = "containerswap_migration_check"


@pytest.fixture
def scratch_url() -> str:
    """A throwaway database, so upgrading does not disturb the suite's own schema."""
    admin = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}"'))
        conn.execute(text(f'CREATE DATABASE "{SCRATCH_DB}"'))
    admin.dispose()

    # render_as_string, not str(): str() masks the password as *** and the
    # connection then fails authentication.
    yield (
        make_url(settings.database_url)
        .set(database=SCRATCH_DB)
        .render_as_string(hide_password=False)
    )

    admin = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}"'))
    admin.dispose()


def test_migrations_match_models(scratch_url):
    config = Config(str(BASE_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BASE_DIR / "migrations"))
    # attributes, not set_main_option: alembic.ini goes through configparser, which
    # chokes on a `%` in the password.
    config.attributes["sqlalchemy_url"] = scratch_url
    command.upgrade(config, "head")

    engine = create_engine(scratch_url)
    try:
        with engine.connect() as conn:
            context = MigrationContext.configure(conn, opts={"compare_type": True})
            diff = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    assert diff == [], (
        "Models and migrations have drifted. Run:\n"
        "  uv run alembic revision --autogenerate -m 'describe the change'\n"
        f"Outstanding differences: {diff}"
    )
