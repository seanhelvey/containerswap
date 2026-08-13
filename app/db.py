from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def _make_engine() -> Engine:
    return create_engine(
        settings.database_url,
        future=True,
        # Production talks to Supabase through PgBouncer in transaction mode, which
        # hands out a different backend per transaction. Server-side prepared
        # statements are bound to one backend, so psycopg's automatic prepare must be
        # off or queries fail intermittently once the threshold is crossed.
        connect_args={"prepare_threshold": None},
        # Pooled connections outlive the server's idea of them — PgBouncer and the
        # platform both cull idle ones. Without this, the first query after an idle
        # spell raises instead of transparently reconnecting.
        pool_pre_ping=True,
        # Deliberately small: zero-downtime deploys run old and new instances at
        # once, and every instance multiplies this against Supabase's pool.
        pool_size=5,
        max_overflow=5,
        pool_recycle=1800,
    )


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
