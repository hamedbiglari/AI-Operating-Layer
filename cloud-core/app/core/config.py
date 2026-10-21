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

    # v4 document intelligence (ADR-122). Provider order is a preference list; an unavailable provider
    # is skipped with its reason recorded, never silently. Mathpix sends the document OFF this
    # deployment, so it is opt-in: it is only tried when both credentials are set.
    DOCUMENT_PROVIDER_ORDER: str = "local_pdf,mathpix,markitdown,image_ocr"
    DOCUMENT_MAX_PAGES: int = 2000
    # Largest request body accepted at all: the 50 MiB upload limit plus multipart overhead (SEC-16).
    MAX_REQUEST_BODY_BYTES: int = 51 * 1024 * 1024
    # below this overall extraction confidence the next provider is tried and, if none does better,
    # the extraction is flagged for human review
    DOCUMENT_MIN_CONFIDENCE: float = 0.5
    MATHPIX_APP_ID: str | None = None
    MATHPIX_APP_KEY: SecretStr | None = None
    MATHPIX_API_BASE_URL: str = "https://api.mathpix.com"
    MATHPIX_POLL_TIMEOUT_SECONDS: int = 600
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
    # ADR-131: an AI job's worker lease, renewed before every item. Must exceed one provider call.
    AI_JOB_LEASE_SECONDS: int = 900
    # How many times a capacity-blocked job resumes by itself before it waits for the user.
    AI_JOB_MAX_AUTO_RESUMES: int = 24
    # How often Celery beat runs ai_center.recover_jobs.
    AI_JOB_RECOVERY_INTERVAL_SECONDS: int = 120

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
    # Prompt-injection defences (ADR-126). The system policy (rules + canary in the provider's system channel)
    # and output checks apply to every AI job. With quarantine on, source text scored "high" is withheld from
    # the model and replaced by a visible placeholder; off = it is still sent (fenced) but flagged.
    AI_SYSTEM_POLICY_ENABLED: bool = True
    PROMPT_INJECTION_QUARANTINE: bool = True
    # Password sign-in throttling (security audit SEC-02). Per address per minute, and per account over 15 minutes.
    LOGIN_PASSWORD_IP_LIMIT_PER_MINUTE: int = 20
    LOGIN_PASSWORD_ACCOUNT_LIMIT_PER_15_MIN: int = 10
    # The legacy password registration endpoint (/auth/register-organization) skips the emailed-code check of
    # the sign-up flow. None = enabled outside production only; set true to allow it in production (SEC-03).
    PASSWORD_REGISTRATION_ENABLED: bool | None = None
    REGISTRATION_IP_LIMIT_PER_HOUR: int = 10
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
    # Needed only when the website runs on a different origin than the API AND uses the browser-session
    # cookie: without it the browser will not send that cookie cross-origin. It widens nothing by itself —
    # only the explicitly configured origins are ever allowed — but it stays off by default.
    CORS_ALLOW_CREDENTIALS: bool = False

    # --- Security ---
    SECRET_KEY: str = _DEFAULT_SECRET_KEY
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ALGORITHM: str = "HS256"

    # --- Browser session: refresh token in an HttpOnly cookie, access token in memory (ADR-129) ---
    # A page cannot read an HttpOnly cookie, so a cross-site script cannot steal the long-lived half
    # of the session. The access token it exchanges that cookie for never leaves a JavaScript variable,
    # so it dies with the tab rather than sitting in storage waiting to be read.
    BROWSER_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    # Absolute lifetime. Rotation issues a new secret but never extends this, so a stolen cookie
    # cannot be refreshed forever.
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    SESSION_COOKIE_NAME: str = "aiol_session"
    # "strict" is correct when the site and the API share a registrable domain (example.com and
    # api.example.com are same-site). Only a genuinely cross-site deployment needs "none", which the
    # validator below then requires to be Secure.
    SESSION_COOKIE_SAMESITE: str = "strict"
    SESSION_COOKIE_DOMAIN: str | None = None

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

    @property
    def session_cookie_secure(self) -> bool:
        """A session cookie is Secure everywhere except local development, which is served over
        plain http and would otherwise never receive the cookie at all."""
        return not self.is_development

    @property
    def session_cookie_path(self) -> str:
        """The cookie is scoped to the session endpoints, so it is never attached to a chat or
        knowledge request — those carry the bearer token instead."""
        return f"{self.API_V1_PREFIX}/auth/session"

    @property
    def password_registration_enabled(self) -> bool:
        if self.PASSWORD_REGISTRATION_ENABLED is None:
            return not self.is_production
        return self.PASSWORD_REGISTRATION_ENABLED

    @model_validator(mode="after")
    def forbid_insecure_defaults_in_production(self) -> "Settings":
        """Fail fast rather than silently boot an insecure production app.

        This is a direct fix for the Phase 0 review finding: a deployment
        that sets APP_ENV=production while forgetting to override
        SECRET_KEY or the database password must refuse to start, not run
        with development credentials.
        """
        # The default signing key is published in the source: any non-local environment running with it
        # accepts forged tokens for every tenant. Only development and test may use it (security audit SEC-09).
        samesite = self.SESSION_COOKIE_SAMESITE.lower()
        if samesite not in ("strict", "lax", "none"):
            raise InsecureProductionConfigError(
                f"SESSION_COOKIE_SAMESITE must be strict, lax or none (got {self.SESSION_COOKIE_SAMESITE!r})")
        # SameSite=None without Secure is rejected by every current browser, so the cookie would simply
        # never be stored: a silent, total loss of the session rather than a visible error.
        if samesite == "none" and not self.session_cookie_secure:
            raise InsecureProductionConfigError(
                "SESSION_COOKIE_SAMESITE=none requires a Secure cookie, which development mode does not set")
        if self.SECRET_KEY == _DEFAULT_SECRET_KEY and self.APP_ENV.lower() not in ("development", "test"):
            raise InsecureProductionConfigError(
                f"Refusing to start with APP_ENV={self.APP_ENV}: SECRET_KEY is still the published development default")
        if not self.is_production:
            return self

        problems: list[str] = []
        if self.SECRET_KEY == _DEFAULT_SECRET_KEY:
            problems.append("SECRET_KEY is still the development default")
        elif len(self.SECRET_KEY) < 32:
            problems.append("SECRET_KEY must be at least 32 characters")
        if _DEFAULT_DB_PASSWORD_MARKER in self.DATABASE_URL:
            problems.append("DATABASE_URL still contains the development password")
        if self.APP_DEBUG:
            problems.append("APP_DEBUG must be false in production")
        if (self.PAYMENT_PROVIDER or "").strip().lower() == "sandbox":
            # The sandbox provider lets an admin self-sign a "payment succeeded" event (SEC-06).
            problems.append("PAYMENT_PROVIDER=sandbox credits wallets without real payment")

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
