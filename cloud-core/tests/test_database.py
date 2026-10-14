"""
Direct database connectivity test.

Requires a reachable PostgreSQL instance at settings.DATABASE_URL
(the docker-compose 'postgres' service). Skips gracefully if the
database is unreachable, so `pytest` still runs in environments
without Docker.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db.session import engine


def test_database_connection() -> None:
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar_one()
            assert result == 1
    except OperationalError:
        pytest.skip("PostgreSQL is not reachable in this environment")


def test_pgvector_extension_available() -> None:
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            ).fetchone()
            assert row is not None, "pgvector extension not installed; run alembic upgrade head"
    except OperationalError:
        pytest.skip("PostgreSQL is not reachable in this environment")
