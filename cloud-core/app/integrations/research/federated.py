"""
The project's one real ResearchProvider: federated scholarly discovery.

Until this adapter existed, `get_research_provider()` could only return
NotConfiguredResearchProvider, so every ResearchTask ended FAILED with "no provider is
configured" — including the tasks an approved chat research request creates (ADR-130).
Meanwhile the repository already had real, tested HTTP clients for three scholarly APIs that
need no API key (Crossref, PubMed/E-utilities, Europe PMC) and a discovery engine that
deduplicates their records into Source rows with an honest access state. Nothing was missing
except the adapter between the two, which is this file.

It is NOT a second research engine. It calls `federated_research_service.discover()` — the same
function the /research/federated endpoints use — so a task-driven run leaves exactly the same
trail (research_queries -> research_provider_runs -> research_hits -> sources) and obeys the
same honesty rules: a returned record proves EXISTENCE, not access; `content_access` stays
`metadata_only`/`abstract_only`; no claim and no evidence row is ever written by discovery.

WHY IT TAKES A SESSION
A discovery provider's entire output is rows that did not exist before the call, and a
ResearchTaskReference can only point at a row that already exists. So the provider is
constructed with the session, tenant and task of the execution it serves. The `ResearchProvider`
Protocol in base.py is unchanged — `run(task_type=..., query=...)` — what changed is that
`get_research_provider()` may now be handed that context to bind.

WHAT IT NEVER REPORTS
`RESULT_INACCESSIBLE` is not in this provider's vocabulary, deliberately. It never downloads
full text and never claims to have read a paper, so it is never in a position to say "found but
unreachable": what it found is metadata, which it got. Access lives on the Source row, where the
acquisition paths and `content_access` state describe exactly what the system holds.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.integrations.research.base import (
    ResearchOutcome, ResearchOutcomeStatus, ResearchReference,
)
from app.integrations.research.scholarly import plain_text_query
from app.models.research_task import ResearchTask

# Crossref's query.bibliographic and Europe PMC's `query` both take a bare string; a chat
# question is natural language, so the operators and quotes a boolean query would carry are
# dropped rather than passed through as literal search terms.
MAX_QUERY_CHARS = 1000


class FederatedResearchProvider:
    """One ResearchTask's query, asked of every configured scholarly API."""

    name = "federated_scholarly"

    def __init__(self, db: Session, *, organization_id: UUID, task: ResearchTask,
                 providers: list | None = None, limit: int = 20) -> None:
        self._db = db
        self._organization_id = organization_id
        self._task = task
        self._providers = providers
        self._limit = limit

    def run(self, *, task_type: str, query: str) -> ResearchOutcome:
        # Imported here, not at module scope: federated_research_service imports
        # research_task_service, which imports base.py, which reaches this module.
        from app.services import federated_research_service

        text = plain_text_query(query or "")[:MAX_QUERY_CHARS].strip()
        if not text:
            return ResearchOutcome(
                status=ResearchOutcomeStatus.NO_RESULT_FOUND,
                summary="The task's query had no searchable words once search operators were removed.",
            )

        out = federated_research_service.discover(
            self._db, organization_id=self._organization_id, research_task=self._task,
            query_text=text, mode="single", route="general",
            providers=self._providers, limit=self._limit,
        )
        runs = out["providers"]
        reached = [r for r in runs if r["status"] == "ok"]

        if not reached:
            # Every provider is either absent or broken, and those are different facts: a
            # deployment with no web search API configured must not be reported as an outage.
            unconfigured = [r["provider"] for r in runs if r["status"] == "not_configured"]
            failed = [f"{r['provider']}: {r['error']}" for r in runs if r["status"] == "failed"]
            if failed:
                return ResearchOutcome(
                    status=ResearchOutcomeStatus.PROVIDER_FAILED,
                    summary="No research provider could be reached — " + "; ".join(failed),
                    raw=out,
                )
            return ResearchOutcome(
                status=ResearchOutcomeStatus.NOT_CONFIGURED,
                summary=("No scholarly provider is configured on this Cloud Core "
                         f"({', '.join(unconfigured) or 'none registered'})."),
                raw=out,
            )

        if not out["source_ids"]:
            return ResearchOutcome(
                status=ResearchOutcomeStatus.NO_RESULT_FOUND,
                summary=(f"{len(reached)} provider(s) answered and none had a record for this query: "
                         f"{text!r}."),
                raw=out,
            )

        # Every source this run put in front of the organisation is reported, new or merged: a
        # record that merged into an existing Source still confirmed that source's existence
        # and may have added its abstract, acquisition paths and provider list (upsert_source).
        return ResearchOutcome(
            status=ResearchOutcomeStatus.RESULT_FOUND,
            summary=(f"{out['unique_sources']} source(s) from "
                     f"{', '.join(r['provider'] for r in reached)}: "
                     f"{out['new_sources']} new, {out['merged_duplicates']} merged into existing sources. "
                     "Metadata and abstracts only — no full text was retrieved, and no evidence or claim "
                     "was created."),
            references=[ResearchReference(reference_type="source", reference_id=sid, role="output")
                        for sid in out["source_ids"]],
            raw=out,
        )
