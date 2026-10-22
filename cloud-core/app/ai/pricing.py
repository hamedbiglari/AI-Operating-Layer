"""
Provider pricing resolution (Phase 17). Prices are configuration
(settings.AI_MODEL_PRICING_JSON), never hardcoded. A model with no
configured price has UNKNOWN cost — returned as None, never 0.

This is the estimated PROVIDER cost from reported token usage. It is not
the provider's invoice (actual_provider_cost) and not a customer charge
(billing, future AICostRecord).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Protocol

from app.core.config import settings

_MTOK = Decimal(1_000_000)
_Q = Decimal("0.000001")


@dataclass(frozen=True)
class ModelPrice:
    """Per-million-token (MTok) input/output prices for one provider/model, in a 3-letter currency code."""
    input_per_mtok: Decimal
    output_per_mtok: Decimal
    currency: str


class PricingResolver(Protocol):
    """Looks up the configured price for a provider/model; injectable for tests."""

    def price(self, provider: str, model: str) -> ModelPrice | None:
        """Return the price, or None when unknown (never a zero price)."""


class ConfiguredPricing:
    """PricingResolver backed by a JSON map keyed "provider/model" (defaults to settings.AI_MODEL_PRICING_JSON)."""

    def __init__(self, raw_json: str | None = None) -> None:
        self._raw = raw_json if raw_json is not None else settings.AI_MODEL_PRICING_JSON

    def price(self, provider: str, model: str) -> ModelPrice | None:
        """Return the configured price, or None if pricing is absent or malformed — unknown, never zero."""
        if not self._raw:
            return None
        try:
            entry = json.loads(self._raw).get(f"{provider}/{model}")
            if not entry:
                return None
            return ModelPrice(Decimal(str(entry["input_per_mtok"])), Decimal(str(entry["output_per_mtok"])),
                              str(entry.get("currency", "USD"))[:3])
        except (ValueError, KeyError, TypeError, InvalidOperation, AttributeError):
            return None  # malformed pricing = unknown, never zero


def estimate_from_usage(price: ModelPrice | None, input_tokens: int | None,
                        output_tokens: int | None) -> Decimal | None:
    """Both token counts must be REPORTED; a missing count makes the
    estimate unknown rather than silently under-counted."""
    if price is None or input_tokens is None or output_tokens is None:
        return None
    cost = (price.input_per_mtok * input_tokens + price.output_per_mtok * output_tokens) / _MTOK
    return cost.quantize(_Q)


def reservation_upper_bound(price: ModelPrice | None, *, prompt: str, max_output_tokens: int,
                            attempts: int) -> Decimal | None:
    """Budget-reservation bound only (never persisted as usage): UTF-8
    bytes bound input tokens from above; max_output_tokens bounds output;
    multiplied by the worst-case number of attempts."""
    if price is None:
        return None
    one = (price.input_per_mtok * len(prompt.encode("utf-8"))
           + price.output_per_mtok * max_output_tokens) / _MTOK
    return (one * max(attempts, 1)).quantize(_Q)
