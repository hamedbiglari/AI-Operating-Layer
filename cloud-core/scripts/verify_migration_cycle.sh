#!/usr/bin/env bash
# Verifies the full Alembic migration chain runs cleanly in both
# directions: base -> head -> base -> head. This is deliberately a
# standalone script, NOT a pytest test: cycling the schema with DDL
# (dropping/recreating every table) is incompatible with running
# alongside the transactional, per-test-isolated pytest suite (see
# tests/conftest.py) against the same database — interleaving the two
# would drop tables out from under an in-flight test transaction.
#
# Run this against a real (ideally disposable) Postgres database:
#   DATABASE_URL=postgresql+psycopg://... ./scripts/verify_migration_cycle.sh
# It uses whatever DATABASE_URL is set in the environment or .env.
#
# CI does not run this today (CI's job is the pytest suite starting
# from a fresh database, which already exercises "upgrade to head from
# nothing"); this script is for verifying the DOWNGRADE path, which
# nothing else in the repo exercises automatically.

set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== [1/4] Upgrade to head (from whatever state the DB is in) ==="
alembic upgrade head

echo "=== [2/4] Downgrade all the way to base ==="
alembic downgrade base

echo "=== [3/4] Confirm no application tables remain ==="
python - <<'PY'
from sqlalchemy import create_engine, inspect
from app.core.config import settings

engine = create_engine(settings.DATABASE_URL)
inspector = inspect(engine)
tables = set(inspector.get_table_names()) - {"alembic_version"}
if tables:
    raise SystemExit(f"FAIL: tables still present after downgrade base: {sorted(tables)}")
print("OK: no application tables remain")
PY

echo "=== [4/4] Upgrade back to head ==="
alembic upgrade head

echo "=== Migration cycle verified: base -> head -> base -> head ==="
