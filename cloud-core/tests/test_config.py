"""
Unit tests for production configuration safety. No database required —
`Settings` is instantiated directly with explicit env overrides.
"""

import pytest

from app.core.config import InsecureProductionConfigError, Settings


def test_production_rejects_default_secret_key() -> None:
    with pytest.raises(InsecureProductionConfigError, match="SECRET_KEY"):
        Settings(
            _env_file=None,
            APP_ENV="production",
            APP_DEBUG=False,
            SECRET_KEY="change-me-to-a-random-64-char-secret-in-production",
            DATABASE_URL="postgresql+psycopg://user:realpass@db.internal:5432/prod",
        )


def test_production_rejects_default_database_password() -> None:
    with pytest.raises(InsecureProductionConfigError, match="DATABASE_URL"):
        Settings(
            _env_file=None,
            APP_ENV="production",
            APP_DEBUG=False,
            SECRET_KEY="a-properly-random-production-secret-key-value",
            DATABASE_URL="postgresql+psycopg://aiol:aiol_dev_password@db.internal:5432/prod",
        )


def test_production_rejects_debug_mode() -> None:
    with pytest.raises(InsecureProductionConfigError, match="APP_DEBUG"):
        Settings(
            _env_file=None,
            APP_ENV="production",
            APP_DEBUG=True,
            SECRET_KEY="a-properly-random-production-secret-key-value",
            DATABASE_URL="postgresql+psycopg://user:realpass@db.internal:5432/prod",
        )


def test_production_with_proper_secrets_boots_successfully() -> None:
    settings = Settings(
        _env_file=None,
        APP_ENV="production",
        APP_DEBUG=False,
        SECRET_KEY="a-properly-random-production-secret-key-value",
        DATABASE_URL="postgresql+psycopg://user:realpass@db.internal:5432/prod",
    )
    assert settings.is_production is True


def test_development_allows_defaults() -> None:
    settings = Settings(_env_file=None, APP_ENV="development")
    assert settings.is_development is True
    assert settings.is_production is False
