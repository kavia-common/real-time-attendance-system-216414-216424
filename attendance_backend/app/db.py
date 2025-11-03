import os
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session


# PUBLIC_INTERFACE
def get_database_url() -> str:
    """Return database connection URL from environment.

    Looks for POSTGRES_URL environment variable. This should be configured
    via the deployment environment (.env). The format must be a valid SQLAlchemy
    URL for Postgres, e.g.:
      postgresql+psycopg2://USER:PASSWORD@HOST:PORT/DBNAME
    """
    db_url = os.getenv("POSTGRES_URL", "").strip()
    if not db_url:
        # Keep code runnable without DB; raise a clear error when accessed.
        raise RuntimeError(
            "POSTGRES_URL is not set. Please configure it in the environment (.env)."
        )
    return db_url


_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


def _build_engine() -> Engine:
    """Create a SQLAlchemy engine with sensible defaults for Postgres."""
    url = get_database_url()
    engine = create_engine(
        url,
        pool_pre_ping=True,  # helps avoid stale connections
        future=True,
    )
    return engine


def _get_engine() -> Engine:
    """Get or create the global engine instance."""
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def _get_session_factory() -> sessionmaker:
    """Get or create the global session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=_get_engine(), autoflush=False, autocommit=False, future=True)
    return _SessionLocal


# PUBLIC_INTERFACE
def get_session() -> Session:
    """Return a new SQLAlchemy Session bound to the configured engine."""
    return _get_session_factory()()


# PUBLIC_INTERFACE
@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations.

    Usage:
        with session_scope() as db:
            db.add(obj)
            ...
    """
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# PUBLIC_INTERFACE
def check_connection() -> bool:
    """Simple connectivity check to the database using SELECT 1."""
    try:
        with _get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
