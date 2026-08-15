"""Alembic environment.

The URL comes from app settings, not alembic.ini, so there is one source of truth
and no connection string is ever committed. It resolves to CS_MIGRATION_DATABASE_URL
when set — in production that must be Supabase's *direct* connection (port 5432),
because DDL through the transaction pooler is unreliable.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app import models  # noqa: F401  (imported for its side effect: registers mappers)
from app.config import settings
from app.db import Base

config = context.config

# Commands that only read from the database — never generate or apply DDL. These
# stay exempt from CS_CONFIRM_PROD_MIGRATION below: gating `alembic current` broke
# the pre-push hook's own read-only schema check, which needs to run on every push
# with no confirmation involved. Anything not in this list (upgrade, downgrade,
# stamp, ...) defaults to requiring confirmation — safer to over-gate an unfamiliar
# command than to silently exempt a write.
_READ_ONLY_COMMANDS = {"current", "history", "heads", "show", "branches", "check", "revision"}


def _url() -> str:
    """Resolve the target URL, deliberately avoiding alembic.ini.

    The URL never goes through config.set_main_option: alembic.ini is parsed by
    configparser, which treats `%` as interpolation syntax and raises on any
    password containing one. config.attributes is a plain dict, so tests can inject
    a scratch URL here without that hazard.

    CS_MIGRATION_DATABASE_URL is safe to leave sitting in .env: it is only ever
    set to production (local dev wants it empty, see Settings.migration_database_url),
    and pydantic-settings loads .env into every process regardless of Docker. Without
    this gate, `alembic upgrade head` — run by habit, or by a script that didn't mean
    to — would silently apply DDL to production. CS_CONFIRM_PROD_MIGRATION must never
    go in .env; it only means anything typed inline, once, for that command.
    """
    override = config.attributes.get("sqlalchemy_url")
    if override:
        return override
    cmd_opts = getattr(config, "cmd_opts", None)
    command_name = cmd_opts.cmd[0].__name__ if cmd_opts and cmd_opts.cmd else None
    needs_confirmation = command_name not in _READ_ONLY_COMMANDS
    if (
        needs_confirmation
        and settings.migration_database_url
        and not os.environ.get("CS_CONFIRM_PROD_MIGRATION")
    ):
        raise RuntimeError(
            "CS_MIGRATION_DATABASE_URL is set, which targets production. Re-run with "
            "CS_CONFIRM_PROD_MIGRATION=yes to confirm that's what you mean to do."
        )
    return settings.alembic_url


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
