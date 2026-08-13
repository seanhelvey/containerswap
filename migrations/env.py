"""Alembic environment.

The URL comes from app settings, not alembic.ini, so there is one source of truth
and no connection string is ever committed. It resolves to CS_MIGRATION_DATABASE_URL
when set — in production that must be Supabase's *direct* connection (port 5432),
because DDL through the transaction pooler is unreliable.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app import models  # noqa: F401  (imported for its side effect: registers mappers)
from app.config import settings
from app.db import Base

config = context.config


def _url() -> str:
    """Resolve the target URL, deliberately avoiding alembic.ini.

    The URL never goes through config.set_main_option: alembic.ini is parsed by
    configparser, which treats `%` as interpolation syntax and raises on any
    password containing one. config.attributes is a plain dict, so tests can inject
    a scratch URL here without that hazard.
    """
    return config.attributes.get("sqlalchemy_url") or settings.alembic_url


if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Catch column type drift, not just added/dropped columns.
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
