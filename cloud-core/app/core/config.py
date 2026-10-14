"""
Centralized application configuration.

All configuration MUST be sourced from environment variables (or a local
.env file during development). No secrets are hard-coded here.

This module is intentionally the single place the rest of the codebase
imports settings from, so environment handling never gets duplicated.

Phase 1 addition (per Phase 0 review, "Production configuration safety"):
the default development credentials are convenient locally but must never
silently reach a production deployment. `Settings` fails fast at startup
if APP_ENV=production and any secret still holds its insecure default.
"""

from functools import lru_cache

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Sentinel defaults. These exist ONLY to make local `docker compose up`
# work out of the box. They are explicitly rejected in production — see
# `Settings.forbid_insecure_defaults_in_production` below.
_DEFAULT_SECRET_KEY = "change-me-to-a-random-64-char-secret-in-production"
_DEFAULT_DB_PASSWORD_MARKER = "aiol_dev_password"


class InsecureProductionConfigError(RuntimeError):
    """Raised when APP_ENV=production but insecure defaults are still set."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Application ---
    APP_ENV: str = "development"
    APP_NAME: str = "AI Operating Layer"
    APP_DEBUG: bool = True
    # Phase 13: displayed in the merchant dashboard next to the plugin
    # version, so a support conversation starts with two known numbers
    # instead of a guess. Kept in one place; the plugin reads it from
    # /telemetry/health rather than holding a second copy.
    CORE_VERSION: str = "0.13.0"

    # --- API ---
    API_V1_PREFIX: str = "/api/v1"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # --- Database ---
    DATABASE_URL: str = "postgresql+psycopg://aiol:aiol_dev_password@postgres:5432/aiol"

    # --- Redis / Queue ---
    REDIS_URL: str = "redis://redis:6379/0"

    # --- Phase 17: AI model providers (AIExecution) ---
    # Credentials come ONLY from the environment / .env (never source,
    # tests, logs, AIExecution rows or API responses). Unset = the provider
    # is not configured and no model call is attempted.
    ANTHROPIC_API_KEY: SecretStr | None = None
    ANTHROPIC_API_BASE_URL: str = "https://api.anthropic.com"
    OPENAI_API_KEY: SecretStr | None = None
    OPENAI_API_BASE_URL: str = "https://api.openai.com"
    AI_PROVIDER_TIMEOUT_SECONDS: float = 30.0
    # Hard cap on a provider response body; larger is recorded as a failed
    # (invalid_response) execution rather than buffered without limit.
    AI_MAX_RESPONSE_BYTES: int = 1_000_000
    # Prices are configuration, never hardcoded (owner §87). JSON object
    # keyed "provider/model": {"input_per_mtok": "..", "output_per_mtok":
    # "..", "currency": "USD"}. A model absent here has UNKNOWN cost (NULL),
    # never 0.
    AI_MODEL_PRICING_JSON: str | None = None
    AI_VISIBILITY_MODEL: str = "claude-haiku-4-5-20251001"
    # Comma-separated "provider/model" fallback targets, tried in order.
    AI_VISIBILITY_FALLBACK_TARGETS: str = ""
    AI_VISIBILITY_MAX_OUTPUT_TOKENS: int = 400
    AI_ATTEMPTS_PER_TARGET: int = 2
    # A RUNNING execution older than this is treated as lost by its worker.
    # Must exceed AI_PROVIDER_TIMEOUT_SECONDS by a wide margin.
    AI_EXECUTION_STALE_SECONDS: int = 900
    # How often Celery beat runs ai_executions.reclaim_stale.
    AI_EXECUTION_RECLAIM_INTERVAL_SECONDS: int = 300

    # --- AI Center (REQ-AIC-*) ---
    # Fernet key (urlsafe base64, 32 bytes) used to encrypt provider
    # credentials at rest. Unset = credentials cannot be stored.
    AI_CREDENTIAL_KEY: SecretStr | None = None
    # Optional semantic memory backend (Walrus). Unset = native memory only.
    WALRUS_API_URL: str | None = None
    WALRUS_DELEGATE_KEY: SecretStr | None = None

    # --- Email one-time login code (owner requirement, phases 1/13) ---
    LOGIN_CODE_TTL_SECONDS: int = 300          # owner gave no lifetime; = resend window (INFERENCE)
    LOGIN_CODE_RESEND_SECONDS: int = 300       # owner: resend after 5 minutes
    LOGIN_CODE_MAX_FAILURES: int = 3           # owner: 3 wrong codes -> lock
    LOGIN_CODE_FIRST_LOCK_SECONDS: int = 3600  # owner: 1 hour
    LOGIN_CODE_SECOND_LOCK_SECONDS: int = 86400  # owner: 24 hours, then contact support
    LOGIN_CODE_IP_LIMIT_PER_MINUTE: int = 30
    # SMTP delivery. Unset SMTP_HOST = delivery not configured: no code is
    # created and the request is refused honestly (never a fake "sent").
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: SecretStr | None = None
    SMTP_STARTTLS: bool = True
    SMTP_FROM: str = "no-reply@localhost"

    # --- Demand Intelligence connectors (REQ-DI). Unset = BLOCKED_EXTERNAL_DEPENDENCY. ---
    GSC_OAUTH_CLIENT_ID: str | None = None
    GSC_OAUTH_CLIENT_SECRET: SecretStr | None = None
    GA4_OAUTH_CLIENT_ID: str | None = None
    GA4_OAUTH_CLIENT_SECRET: SecretStr | None = None

    # --- Federated research providers (Crossref / NCBI / Europe PMC need no key; polite contact) ---
    RESEARCH_CONTACT_EMAIL: str | None = None
    NCBI_API_KEY: SecretStr | None = None

    # --- VPN / proxy advisory on the login page: X-Forwarded-For entries added by OUR OWN infrastructure ---
    TRUSTED_PROXY_HOPS: int = 0

    # --- Payments (ADR-104). None = no provider (BLOCKED_EXTERNAL_DEPENDENCY). 'sandbox' = development only. ---
    PAYMENT_PROVIDER: str | None = None
    PAYMENT_WEBHOOK_SECRET: SecretStr | None = None
    PAYMENT_WEBHOOK_TOLERANCE_SECONDS: int = 300
    WALLET_CURRENCY: str = "USD"

    # --- Phase 17: browser dashboard access ---
    # Comma-separated exact origins allowed to call the API from a browser
    # (GET, and PATCH for Settings). Empty = no CORS. Never "*".
    CORS_ALLOWED_ORIGINS: str = ""

    # --- Security ---
    SECRET_KEY: str = _DEFAULT_SECRET_KEY
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ALGORITHM: str = "HS256"

    # --- Embeddings ---
    # Kept configurable so the vector dimension is never hard-coded into
    # migrations/models in a way that blocks switching embedding models.
    EMBEDDING_DIMENSIONS: int = 1536

    # --- Logging ---
    LOG_LEVEL: str = "INFO"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV.lower() == "development"

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @model_validator(mode="after")
    def forbid_insecure_defaults_in_production(self) -> "Settings":
        """Fail fast rather than silently boot an insecure production app.

        This is a direct fix for the Phase 0 review finding: a deployment
        that sets APP_ENV=production while forgetting to override
        SECRET_KEY or the database password must refuse to start, not run
        with development credentials.
        """
        if not self.is_production:
            return self

        problems: list[str] = []
        if self.SECRET_KEY == _DEFAULT_SECRET_KEY:
            problems.append("SECRET_KEY is still the development default")
        if _DEFAULT_DB_PASSWORD_MARKER in self.DATABASE_URL:
            problems.append("DATABASE_URL still contains the development password")
        if self.APP_DEBUG:
            problems.append("APP_DEBUG must be false in production")

        if problems:
            raise InsecureProductionConfigError(
                "Refusing to start with APP_ENV=production: " + "; ".join(problems)
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (env is read once per process)."""
    return Settings()


settings = get_settings()
