from sqlalchemy.schema import CreateTable, CreateIndex
from sqlalchemy.dialects import postgresql
import re
import app.models
from app.db.base import Base
from app.models.ai_execution import AIExecution, TRIGGER_STATEMENTS, composite_fk_statements
order = ["ai_providers", "ai_provider_accounts", "ai_models", "ai_health_events", "ai_routing_policies",
         "ai_routing_steps", "ai_routing_decisions", "ai_working_memory", "ai_discovery_entries", "knowledge_keywords",
         "ai_jobs", "ai_job_items"]
d = postgresql.dialect(); up = []
for name in order:
    t = Base.metadata.tables[name]
    up.append(str(CreateTable(t).compile(dialect=d)).strip())
    for ix in sorted(t.indexes, key=lambda i: i.name):
        up.append(str(CreateIndex(ix).compile(dialect=d)).strip())
up += ["ALTER TABLE ai_executions ADD COLUMN provider_account_id UUID", "ALTER TABLE ai_executions ADD COLUMN stop_reason VARCHAR(40)",
       "ALTER TABLE ai_executions ADD COLUMN ai_job_id UUID",
       "CREATE INDEX ix_ai_executions_provider_account_id ON ai_executions (provider_account_id)",
       "CREATE INDEX ix_ai_executions_ai_job_id ON ai_executions (ai_job_id)"]
cks = {str(c.name): c.sqltext.text for c in AIExecution.__table__.constraints if getattr(c, "sqltext", None) is not None}
for short in ["parent_type_known", "arc_cardinality", "parent_type_matches", "attempt_reason"]:
    full = f"ck_ai_executions_{short}"
    up += [f"ALTER TABLE ai_executions DROP CONSTRAINT {full}", f"ALTER TABLE ai_executions ADD CONSTRAINT {full} CHECK ({cks[full]})"]
up += [s for s in composite_fk_statements() if "fk_ai_executions_provider_account" in s or "fk_ai_executions_ai_job" in s]
up += TRIGGER_STATEMENTS
old = {"parent_type_known": "parent_type IN ('visibility_run')", "arc_cardinality": "num_nonnulls(visibility_run_id) <= 1",
       "parent_type_matches": "visibility_run_id IS NULL OR parent_type = 'visibility_run'",
       "attempt_reason": "attempt_reason IS NULL OR attempt_reason IN ('retry', 'manual_retry', 'provider_fallback', 'model_fallback')"}
down = ["ALTER TABLE ai_executions DROP CONSTRAINT IF EXISTS fk_ai_executions_provider_account",
        "ALTER TABLE ai_executions DROP CONSTRAINT IF EXISTS fk_ai_executions_ai_job"]
down += [f"ALTER TABLE ai_executions DROP CONSTRAINT IF EXISTS ck_ai_executions_{s}" for s in old]
down += ["DROP INDEX IF EXISTS ix_ai_executions_provider_account_id", "DROP INDEX IF EXISTS ix_ai_executions_ai_job_id",
         "ALTER TABLE ai_executions DROP COLUMN IF EXISTS stop_reason", "ALTER TABLE ai_executions DROP COLUMN IF EXISTS provider_account_id",
         "ALTER TABLE ai_executions DROP COLUMN IF EXISTS ai_job_id"]
down += [f"ALTER TABLE ai_executions ADD CONSTRAINT ck_ai_executions_{s} CHECK ({sql})" for s, sql in old.items()]
down += [f"DROP TABLE IF EXISTS {n}" for n in reversed(order)]
p = "migrations/versions/0020_ai_center.py"; body = open(p).read()
body = re.sub(r"_UP = \[.*?\]\n", lambda m: "_UP = " + repr(up) + "\n", body, count=1, flags=re.S)
body = re.sub(r"_DOWN = \[.*?\]\n", lambda m: "_DOWN = " + repr(down) + "\n", body, count=1, flags=re.S)
if "AI jobs" not in body:
    body = body.replace("per-Knowledge-Object keyword workspace. Adds provider_account_id and\nstop_reason to ai_executions",
        "per-Knowledge-Object keyword workspace, and AI jobs (multi-item processing,\nthe new exclusive-arc parent `ai_job_id`). Adds provider_account_id, ai_job_id and\nstop_reason to ai_executions")
open(p, "w").write(body); print(len(up), "up /", len(down), "down; ai_jobs present:", "CREATE TABLE ai_jobs" in body)
