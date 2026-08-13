from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def _make_engine() -> Engine:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    return create_engine(
        f"sqlite:///{settings.db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection, _record):
    cur = dbapi_connection.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


def init_db() -> None:
    from app import models  # noqa: F401  (register mappers)

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


def _add_missing_columns() -> None:
    """Add columns that exist on a model but not yet in the table.

    `create_all` only creates missing tables, so a new column would otherwise
    break an existing database. This covers additive changes, which is most of
    them early on. Anything else — renames, drops, backfills, type changes —
    needs a real migration tool; bring in Alembic at that point rather than
    growing this function.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existing = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                if not column.nullable and column.server_default is None:
                    # Cannot be added to existing rows without a default.
                    raise RuntimeError(
                        f"{table.name}.{column.name} is NOT NULL with no server "
                        "default; this needs a real migration."
                    )
                ddl = column.type.compile(engine.dialect)
                if column.server_default is not None:
                    # Without this, existing rows get NULL instead of the default.
                    ddl += f" DEFAULT {column.server_default.arg.text}"
                conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {ddl}"))


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
