"""
Database engine and session management.

Exposes:
- `engine`: the shared SQLAlchemy engine
- `SessionLocal`: session factory
- `get_db`: FastAPI dependency yielding a scoped session per-request
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# Every session runs in UTC, so timestamps the API returns carry +00:00 whatever the server's local zone is.
CONNECT_ARGS = {"options": "-c timezone=UTC"}

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    future=True,
    connect_args=CONNECT_ARGS,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    future=True,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a DB session and guarantees it is closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
