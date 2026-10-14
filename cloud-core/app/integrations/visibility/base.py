"""
Visibility provider boundary (P12-18, ADR-074).

Follows the pattern already established in `app/integrations/research/base.py`
and `embeddings/base.py`: a `Protocol` plus a `NotConfigured*` default. That
is a deliberate reuse of an existing convention, not a new one.

THE RULE THIS BOUNDARY ENFORCES

A provider that cannot run must report `NOT_CONFIGURED` or `UNAVAILABLE` —
never an empty result. "We could not ask" and "we asked and the brand was
absent" are different findings, and a provider returning `[]` for the first
would silently manufacture the second.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.models.enums import ProviderOutcome, SignalPresence, VisibilityPlatform


@dataclass
class ProbeSignals:
    """Tri-state per signal, defaulting to NOT_CHECKED.

    A provider that does not examine citation leaves it NOT_CHECKED rather
    than ABSENT — the distinction ADR-061 exists to protect."""

    mentioned: SignalPresence = SignalPresence.NOT_CHECKED
    cited: SignalPresence = SignalPresence.NOT_CHECKED
    recommended: SignalPresence = SignalPresence.NOT_CHECKED
    product_present: SignalPresence = SignalPresence.NOT_CHECKED
    url_present: SignalPresence = SignalPresence.NOT_CHECKED


@dataclass
class ProbeResult:
    """One provider probe. `outcome` is authoritative.

    When `outcome` is anything other than SUCCESS, the signals are
    meaningless and a caller must not read them as findings — which is why
    they default to NOT_CHECKED rather than ABSENT.
    """

    outcome: ProviderOutcome
    platform: VisibilityPlatform
    prompt: str
    signals: ProbeSignals = field(default_factory=ProbeSignals)
    response_text: str | None = None
    platform_model: str | None = None
    estimated_cost: float = 0.0
    actual_cost: float | None = None
    parser_version: str = "v1"
    error: str | None = None
    raw: dict = field(default_factory=dict)
    # Fixture data must never be mistaken for a live observation (§44).
    is_fixture: bool = False
    # Phase 17: terminal AIExecution of this probe's chain; None when no
    # model was invoked (fixture / not configured).
    ai_execution_id: object | None = None
    # Phase 17: what the budget reservation should settle to. 0.0 when no
    # model was invoked (nothing can have been spent); the summed estimated
    # cost of every execution in the chain when all are known; None when
    # any is unknown, in which case the full reservation is kept (never
    # under-counts spend).
    budget_settlement: float | None = None

    @property
    def usable(self) -> bool:
        return self.outcome in (ProviderOutcome.SUCCESS, ProviderOutcome.PARTIAL)


class VisibilityProvider(Protocol):
    """Anything that can probe one platform with one prompt."""

    name: str
    version: str

    def probe(
        self, *, platform: VisibilityPlatform, prompt: str,
        market: str | None = None, language: str | None = None,
        target_brand: str | None = None, target_domain: str | None = None,
    ) -> ProbeResult:
        """Must NEVER raise for an ordinary failure. Provider unavailability,
        rate limiting and auth problems are `ProviderOutcome` values, not
        exceptions — a raise would force the caller to guess which of them
        occurred."""
        ...

    def estimate_cost(self, *, platform: VisibilityPlatform, prompt: str) -> float | None:
        """Returns None when the cost genuinely cannot be determined.

        None must NOT be read as zero (§28): an unknown cost requires
        explicit authorization, whereas zero would silently authorise
        unlimited spend."""
        ...


class NotConfiguredVisibilityProvider:
    """**The default provider.** No AI platform credentials exist in this
    environment, and none are fabricated.

    Every probe returns NOT_CONFIGURED with all signals NOT_CHECKED. That
    is the honest result: nothing was asked, so nothing is known. A
    provider returning empty-but-successful would convert "we did not ask"
    into "the brand is absent", which is precisely the fabrication §44
    forbids.
    """

    name = "not_configured"
    version = "1.0"

    def probe(
        self, *, platform: VisibilityPlatform, prompt: str,
        market: str | None = None, language: str | None = None,
        target_brand: str | None = None, target_domain: str | None = None,
    ) -> ProbeResult:
        return ProbeResult(
            outcome=ProviderOutcome.NOT_CONFIGURED,
            platform=platform,
            prompt=prompt,
            signals=ProbeSignals(),  # all NOT_CHECKED
            error=(
                f"No visibility provider is configured for {platform.value}. "
                "No observation was made; this is not evidence of absence."
            ),
        )

    def estimate_cost(self, *, platform: VisibilityPlatform, prompt: str) -> float | None:
        return 0.0  # a probe that never runs costs nothing
