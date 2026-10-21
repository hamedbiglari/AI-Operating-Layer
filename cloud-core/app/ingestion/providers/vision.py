"""
Vision interpretation of figures — contract only (prompt v4.0 §8.6, §12; extraction level 4).

FACT: both LLM adapters in this codebase (`integrations/llm/anthropic.py`, `openai.py`) send text prompts
only; neither sends image content. A vision provider therefore cannot be built on them without first
extending the adapter contract, which is a change to the Phase 16 invocation lock and needs its own ADR.

So this module defines the contract and reports itself unavailable. It does not pretend: there is no
code path that writes `vision_description` today, and `DocumentAsset.vision_model` stays NULL.

When it is built, a figure interpretation MUST:
  * be stored as an interpretation of a located figure (element `figure`, method `vision`), never as
    the figure's text;
  * carry the model and version that produced it;
  * never raise evidence strength — a model reading a chart is not a study (§8.6, §27).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.ingestion.providers.base import Availability


@dataclass
class FigureInterpretation:
    labels: list[str]
    chart_type: str | None
    axes: dict | None
    legend: list[str] | None
    data_points: list[dict] | None
    description: str
    model: str
    model_version: str | None
    confidence: float | None


class VisionInterpretationProvider:
    name = "vision"

    def availability(self) -> Availability:
        return Availability(False, "no vision-capable adapter: the LLM adapter contract is text-only "
                                   "(see module docstring)")

    def interpret_figure(self, image: bytes, *, caption: str | None = None) -> FigureInterpretation:
        raise NotImplementedError("vision interpretation is not built; availability() says why")
