"""
Celery application instance — the "worker execution foundation" master
spec section 17 asks Phase 5 to build on top of. `app/workers/` was
empty scaffolding through Phase 4 (see docs/development.md's Phase 3
STATUS note); this is the first real task wired up.

Broker/backend both point at `settings.REDIS_URL` (already configured
since Phase 0, previously unused). Results are ignored on purpose:
`ResearchTask.status`/`.result` in Postgres are the durable source of
truth for a task's outcome (the same "make the database, not the task
queue, the record of what happened" principle already implicit in every
other service in this codebase) — Celery's own result backend would
just be a second, redundant, more-ephemeral copy of the same
information.
"""

from celery import Celery

from app.core.config import settings

celery_app = Celery("ai_operating_layer", broker=settings.REDIS_URL)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_ignore_result=True,
    # Periodic jobs. They require a `celery beat` process
    # alongside the worker (see docs/phase17/PHASE17_EXCEPTION_REGISTER.md).
    beat_schedule={
        "ai-executions-reclaim-stale": {
            "task": "ai_executions.reclaim_stale",
            "schedule": float(settings.AI_EXECUTION_RECLAIM_INTERVAL_SECONDS),
        },
        # ADR-131: dead workers and reset provider limits.
        "ai-center-recover-jobs": {
            "task": "ai_center.recover_jobs",
            "schedule": float(settings.AI_JOB_RECOVERY_INTERVAL_SECONDS),
        },
    },
)

# Explicit import rather than celery_app.autodiscover_tasks(): this
# project has exactly one task module today, and an explicit import is
# easier to follow than relying on Celery's package-scanning behavior
# for a single file. Add further `import app.workers.<module>` lines
# here as more task modules are introduced.
import app.workers.tasks  # noqa: E402,F401
