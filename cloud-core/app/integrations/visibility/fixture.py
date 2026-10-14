"""
Deterministic fixture visibility provider (P12-18 §35).

FOR TESTS ONLY, and it says so in the data: every result carries
`is_fixture=True`, which persists onto the observation. §44 forbids fixture
data masquerading as live observation, and a boolean on the row is the only
way a consumer can tell.

The fixture deliberately produces DIFFERENT outcomes for different prompts
so that tests exercise the semantic distinctions rather than one happy
path: present, absent, not-checked, unavailable and failed all occur.
"""

from __future__ import annotations

from app.integrations.visibility.base import ProbeResult, ProbeSignals
from app.models.enums import ProviderOutcome, SignalPresence, VisibilityPlatform


class FixtureVisibilityProvider:
    """Routes on a marker in the prompt so a test can request any outcome."""

    name = "fixture"
    version = "1.0"

    def probe(
        self, *, platform: VisibilityPlatform, prompt: str,
        market: str | None = None, language: str | None = None,
        target_brand: str | None = None, target_domain: str | None = None,
    ) -> ProbeResult:
        lowered = prompt.lower()

        if "[unavailable]" in lowered:
            return ProbeResult(
                outcome=ProviderOutcome.UNAVAILABLE, platform=platform, prompt=prompt,
                error="Provider unavailable", is_fixture=True,
            )
        if "[ratelimited]" in lowered:
            return ProbeResult(
                outcome=ProviderOutcome.RATE_LIMITED, platform=platform, prompt=prompt,
                error="Rate limited", is_fixture=True,
            )
        if "[failed]" in lowered:
            return ProbeResult(
                outcome=ProviderOutcome.FAILED, platform=platform, prompt=prompt,
                error="Upstream error", is_fixture=True,
            )
        if "[absent]" in lowered:
            # Genuinely looked and found nothing - a real negative finding.
            return ProbeResult(
                outcome=ProviderOutcome.SUCCESS, platform=platform, prompt=prompt,
                signals=ProbeSignals(
                    mentioned=SignalPresence.ABSENT,
                    cited=SignalPresence.ABSENT,
                    recommended=SignalPresence.ABSENT,
                    url_present=SignalPresence.ABSENT,
                ),
                response_text="No mention of the brand.",
                platform_model="fixture-model-1", estimated_cost=0.01,
                actual_cost=0.008, is_fixture=True,
            )
        if "[partial]" in lowered:
            # Mention examined, citation NOT examined: the case a boolean
            # model cannot express.
            return ProbeResult(
                outcome=ProviderOutcome.PARTIAL, platform=platform, prompt=prompt,
                signals=ProbeSignals(mentioned=SignalPresence.PRESENT),
                response_text="Partial answer.", platform_model="fixture-model-1",
                estimated_cost=0.01, actual_cost=0.004, is_fixture=True,
            )

        return ProbeResult(
            outcome=ProviderOutcome.SUCCESS, platform=platform, prompt=prompt,
            signals=ProbeSignals(
                mentioned=SignalPresence.PRESENT,
                cited=SignalPresence.PRESENT,
                recommended=SignalPresence.ABSENT,
                product_present=SignalPresence.PRESENT,
                url_present=SignalPresence.PRESENT,
            ),
            response_text=f"{target_brand or 'The brand'} is discussed and cited.",
            platform_model="fixture-model-1", estimated_cost=0.01, actual_cost=0.009,
            is_fixture=True,
        )

    def estimate_cost(self, *, platform: VisibilityPlatform, prompt: str) -> float | None:
        if "[unknowncost]" in prompt.lower():
            # Unknown cost must NOT be treated as free (§28).
            return None
        return 0.01


_REGISTRY: dict[str, object] = {}


def register(provider) -> None:
    _REGISTRY[provider.name] = provider


def get_provider(name: str | None = None):
    """Returns the named provider, defaulting to the honest not-configured
    one. An unknown name yields NOT_CONFIGURED rather than raising: a typo
    in configuration must not crash a worker, and must not silently fall
    back to a provider that fabricates results."""
    from app.integrations.visibility.base import NotConfiguredVisibilityProvider

    if not name:
        return NotConfiguredVisibilityProvider()
    return _REGISTRY.get(name) or NotConfiguredVisibilityProvider()


register(FixtureVisibilityProvider())

# Phase 17: the model-backed provider registers itself on import.
from app.integrations.visibility import llm as _llm  # noqa: E402,F401
