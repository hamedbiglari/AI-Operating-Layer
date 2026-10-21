"""
Model-backed visibility provider (Phase 17) — the first domain path that
invokes a real AI model, strictly through the shared invocation wrapper.

HONESTY RULES
  * It observes an Anthropic model, so it serves ONLY platform=OTHER (the
    enum has no Claude value; the actual model is recorded in
    platform_model and on the AIExecution). A run for chatgpt/gemini/etc.
    gets UNAVAILABLE — asking Claude is not observing ChatGPT.
  * Signals it cannot evaluate stay NOT_CHECKED. Parser v1-llm checks only
    brand mention and domain presence (plain substring); cited /
    recommended / product_present are NOT_CHECKED.
  * probe() without an invocation context refuses (UNAVAILABLE) rather
    than calling the model outside the wrapper.
  * No credential => NOT_CONFIGURED and no AIExecution row.
"""
from __future__ import annotations

from app.ai.invocation import (
    InvocationContext, ModelTarget, ProviderNotConfigured, invoke_with_policy,
)
from app.ai.pricing import ConfiguredPricing, reservation_upper_bound
from app.core.config import settings
from app.integrations.llm.base import ModelRequest, get_adapter
from app.integrations.visibility.base import ProbeResult, ProbeSignals
from app.models.enums import AIExecutionStatus, ProviderOutcome, SignalPresence, VisibilityPlatform

PARSER_VERSION = "v1-llm"
SERVED_PLATFORM = VisibilityPlatform.OTHER

_STATUS_TO_OUTCOME = {
    AIExecutionStatus.RATE_LIMITED.value: ProviderOutcome.RATE_LIMITED,
    AIExecutionStatus.TIMEOUT.value: ProviderOutcome.UNAVAILABLE,
}


class LLMVisibilityProvider:
    name = "anthropic"
    version = "1.0"

    def __init__(self, *, adapters: dict | None = None, pricing=None) -> None:  # noqa: ANN001
        self._adapters = adapters
        self._pricing = pricing

    def _targets(self) -> list[ModelTarget]:
        targets = [ModelTarget("anthropic", settings.AI_VISIBILITY_MODEL)]
        for raw in filter(None, (s.strip() for s in settings.AI_VISIBILITY_FALLBACK_TARGETS.split(","))):
            targets.append(ModelTarget.parse(raw))
        return targets

    def _pricing_resolver(self):  # noqa: ANN202
        return self._pricing or ConfiguredPricing()

    def estimate_cost(self, *, platform: VisibilityPlatform, prompt: str) -> float | None:
        if platform is not SERVED_PLATFORM:
            return 0.0  # refused before any call; costs nothing
        bounds = []
        for target in self._targets():
            bound = reservation_upper_bound(
                self._pricing_resolver().price(target.provider, target.model), prompt=prompt,
                max_output_tokens=settings.AI_VISIBILITY_MAX_OUTPUT_TOKENS,
                attempts=settings.AI_ATTEMPTS_PER_TARGET,
            )
            if bound is None:
                return None  # unknown price => unknown cost => run refuses (§28)
            bounds.append(bound)
        return float(sum(bounds))

    def probe(self, *, platform, prompt, market=None, language=None, target_brand=None,  # noqa: ANN001
              target_domain=None) -> ProbeResult:
        return ProbeResult(outcome=ProviderOutcome.UNAVAILABLE, platform=platform, prompt=prompt,
                           error="Model-backed provider requires an AI invocation context")

    def probe_with_context(self, db, ctx: InvocationContext, *, platform, prompt, market=None,  # noqa: ANN001
                           language=None, target_brand=None, target_domain=None) -> ProbeResult:
        if platform is not SERVED_PLATFORM:
            return ProbeResult(outcome=ProviderOutcome.UNAVAILABLE, platform=platform, prompt=prompt,
                               budget_settlement=0.0,
                               error=f"This provider observes Anthropic models only; "
                                     f"it cannot observe {platform.value}")
        try:
            policy = invoke_with_policy(
                db, ctx, self._targets(),
                ModelRequest(prompt=prompt, max_output_tokens=settings.AI_VISIBILITY_MAX_OUTPUT_TOKENS),
                attempts_per_target=settings.AI_ATTEMPTS_PER_TARGET, adapters=self._adapters,
                pricing=self._pricing_resolver(),
            )
        except ProviderNotConfigured:
            policy = None
        if policy is None or policy.not_configured:
            return ProbeResult(outcome=ProviderOutcome.NOT_CONFIGURED, platform=platform, prompt=prompt,
                               budget_settlement=0.0,
                               error="No AI model credential is configured; nothing was asked")

        final = policy.final
        execution = final.execution
        chain_costs = [e.estimated_provider_cost for e in policy.executions]
        settlement = (float(sum(chain_costs)) if all(c is not None for c in chain_costs) else None)
        # estimated_cost is deliberately NOT copied onto the observation: the
        # linked AIExecution(s) own provider cost (single source of truth,
        # admin-only). Copying it would duplicate the fact and expose it to
        # every role through the visibility API.
        base = dict(platform=platform, prompt=prompt, parser_version=PARSER_VERSION,
                    platform_model=execution.model_version or execution.model,
                    estimated_cost=None,
                    actual_cost=None, ai_execution_id=execution.id,
                    budget_settlement=settlement)
        if not final.succeeded:
            return ProbeResult(outcome=_STATUS_TO_OUTCOME.get(execution.status, ProviderOutcome.FAILED),
                               error=execution.error_message, **base)

        text = final.result.text or ""
        lowered = text.lower()

        def presence(needle: str | None) -> SignalPresence:
            if not needle:
                return SignalPresence.NOT_CHECKED
            return SignalPresence.PRESENT if needle.lower() in lowered else SignalPresence.ABSENT

        # The answer is observed, not trusted (ADR-126): signals are read from it as received, but what is stored
        # and later shown has hidden characters, images and HTML removed. URLs stay — citing a site is what a
        # visibility probe measures. The probe prompt itself is the operator's query and is sent unwrapped, so
        # the measurement is not skewed by safety wording.
        from app.ai.prompt_safety import strip_active_content

        return ProbeResult(outcome=ProviderOutcome.SUCCESS, response_text=strip_active_content(text),
                           signals=ProbeSignals(mentioned=presence(target_brand),
                                                url_present=presence(target_domain)), **base)


def _register() -> None:
    from app.integrations.visibility.fixture import register

    register(LLMVisibilityProvider())


_register()
