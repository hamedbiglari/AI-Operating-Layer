"""
NOT IMPORTED BY THE APPLICATION. This package is deliberately named with
a leading underscore and "not_wired" so nothing in app/models/__init__.py
or Alembic's autogenerate target ever picks it up by accident.

Everything here is DESIGNED, not IMPLEMENTED (see docs/DECISIONS.md's
status taxonomy) — draft SQLAlchemy models written for a follow-up
implementation session to start from, syntax-checked with
`python -m py_compile` and reviewed for consistency with PageView /
Organization, but never imported against a real metadata registry, never
migrated, never run. See docs/billing/BILLING_ARCHITECTURE.md.
"""
