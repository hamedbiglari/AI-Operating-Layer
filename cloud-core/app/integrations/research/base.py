"""
ResearchProvider interface (master spec section 18).

Mirrors app/integrations/embeddings/base.py's two-method-interface
pattern: app/services/research_task_service.py depends only on
`ResearchProvider`, never on a concrete implementation, so adding a
real provider later (a web search client, a PubMed/DOI lookup client,
a user-document search over the existing Source/Document/Chunk store,
...) means implementing this interface and changing what
`get_research_provider()` returns — no other code changes.

Section 18 is explicit that the system must be able to tell these
apart, not collapse them into one generic "failure":

  - provider not configured
  - provider failed
  - no result found
  - result found
  - result inaccessible

`ResearchOutcomeStatus` is exactly that five-way distinction.
"""

import enum
from dataclasses import dataclass, field
from typing import Protocol


class ResearchOutcomeStatus(str, enum.Enum):
    NOT_CONFIGURED = "not_configured"
    PROVIDER_FAILED = "provider_failed"
    NO_RESULT_FOUND = "no_result_found"
    RESULT_FOUND = "result_found"
    RESULT_INACCESSIBLE = "result_inaccessible"


@dataclass
class ResearchReference:
    """One thing the provider used or found while executing a task.
    Reference resolution and tenant-checking happen where the DB
    session and org context actually live
    (research_task_service.execute_research_task) — the provider itself
    only reports what it saw, using the string values of
    ResearchReferenceType/ResearchReferenceRole."""

    reference_type: str
    reference_id: str
    role: str = "output"


@dataclass
class ResearchOutcome:
    status: ResearchOutcomeStatus
    summary: str | None = None
    references: list[ResearchReference] = field(default_factory=list)
    raw: dict | None = None


class ResearchProvider(Protocol):
    """Anything that can attempt to execute one ResearchTask's query."""

    def run(self, *, task_type: str, query: str) -> ResearchOutcome:
        """Attempt the research task. Must never raise for an ordinary
        "nothing found" or "not configured" outcome — those are
        ResearchOutcomeStatus values, not exceptions. Only raise for a
        genuine programming error the caller should surface as a bug,
        not as a normal PROVIDER_FAILED result."""
        ...


class NotConfiguredResearchProvider:
    """**The only provider registered by default.** This environment has
    no reachable external research/search API — no web search client,
    scientific-database client, or DOI/PMID lookup — for the same
    reason app/integrations/embeddings/deterministic.py's placeholder
    exists: this sandbox's network allow-list has no such API on it,
    and requiring one would break the project running out of the box
    for anyone who clones this repo.

    Unlike the embedding placeholder, this one does NOT fabricate a
    plausible-looking result — section 18 explicitly forbids that
    ("Do NOT invent fake integrations. Do NOT claim that a search API
    works if no real provider is configured."). It reports
    NOT_CONFIGURED honestly, every time, for every task_type. Every
    ResearchTask executed against this provider will end in FAILED with
    that reason recorded in `result` — this is expected, documented
    behavior for a real environment that has not yet configured a real
    provider, not a bug.
    """

    def run(self, *, task_type: str, query: str) -> ResearchOutcome:
        return ResearchOutcome(
            status=ResearchOutcomeStatus.NOT_CONFIGURED,
            summary=(
                f"No research provider is configured for task_type={task_type!r}. "
                "Implement ResearchProvider (app/integrations/research/base.py) and "
                "register it in get_research_provider() to enable real execution."
            ),
        )


_default_provider: ResearchProvider | None = None


def get_research_provider() -> ResearchProvider:
    """Single shared provider instance, same pattern as
    get_embedding_provider(). Swapping providers later means changing
    this function's return value, not any caller."""
    global _default_provider
    if _default_provider is None:
        _default_provider = NotConfiguredResearchProvider()
    return _default_provider
