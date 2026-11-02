"""The models alone can build the schema (V5-aiagent-model-drift).

The test harness builds missing tables with Base.metadata.create_all(), so a constraint that only a migration creates
makes every DB-backed test fail on a fresh database. This builds every table in a new, empty database (with the two
extensions migration 0001 creates) and drops it again; the migrations are not involved.
"""
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.db.base import Base


def test_create_all_builds_every_table_on_an_empty_database(db_engine) -> None:
    name = "fresh_" + uuid.uuid4().hex[:10]
    url = make_url(settings.DATABASE_URL)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_engine(url.set(database=name))
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
        Base.metadata.create_all(bind=engine)
        with engine.connect() as conn:
            made = conn.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")).scalar_one()
        assert made == len(Base.metadata.tables)
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()
