"""
FastAPI application entrypoint.

Phase 0: app bootstrap, config, logging, request-id middleware,
versioned API mount, and health endpoints.
Phase 1 adds: consistent error envelope, and the auth/organizations/
users/sites routers (tenant-isolated CRUD + JWT authentication).
"""

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware

configure_logging()

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="Knowledge-to-Discovery-to-Commerce Operating Layer — Cloud Core API",
)

app.add_middleware(RequestIdMiddleware)

# Phase 17: browser dashboards call this API cross-origin. Allowed origins
# are explicit configuration; empty (the default) means no CORS headers at
# all — nothing is opened implicitly, and a wildcard is never used.
if settings.CORS_ALLOWED_ORIGINS.strip():
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.CORS_ALLOWED_ORIGINS.split(",") if o.strip()],
        allow_credentials=False,
        # GET for every wired screen; PATCH for Settings; POST/PUT/DELETE for
        # the AI Center (register providers/accounts, set or delete a
        # credential, test connections, import discovery/keywords, control
        # jobs). Still only for explicitly configured origins, bearer-token
        # auth, no cookies (allow_credentials=False).
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
register_exception_handlers(app)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/", tags=["root"])
def root() -> dict:
    return {
        "service": settings.APP_NAME,
        "env": settings.APP_ENV,
        "api": settings.API_V1_PREFIX,
    }
