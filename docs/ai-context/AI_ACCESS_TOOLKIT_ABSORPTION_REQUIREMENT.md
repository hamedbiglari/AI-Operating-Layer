# AI Access Toolkit absorption — binding project requirement

**STATUS: BINDING.** Recorded in the repository so it survives outside any
one conversation.

## The requirement

The AI Access Toolkit is the predecessor of the WordPress adapter. It must
not persist as a separate product. Every capability it had must be
explicitly classified — REUSE / REFACTOR / REPLACE / DEPRECATE / DEFER — in
[`AI_ACCESS_TOOLKIT_CAPABILITY_MAP.md`](AI_ACCESS_TOOLKIT_CAPABILITY_MAP.md),
and retained capabilities must have regression tests.

## Why it is not a simple merge

The legacy plugin and this architecture disagree on a point that matters:

**Legacy:** WordPress computed a readiness score, assembled product schema
from WordPress data, ran its own API with its own keys and its own rate
limiter, and asserted that named AI systems had consumed the content.

**This architecture:** Cloud Core is the source of truth. WordPress is a
projection. Trust is evidence-backed. Unverified data never becomes a
public claim.

So three legacy capabilities were **replaced rather than migrated**:

1. **Structured data** built from WordPress data → Core-backed only. The
   legacy path could publish an unverified value as a schema.org assertion.
2. **The AI Gateway** → Core is the canonical API. A second one in
   WordPress would be a second source of truth by another name.
3. **The readiness score** → a single number is not evidence (ADR-047).

Absorption is not "the code now lives here". It is "the capability is
either present and tested, or explicitly and testably absent".

## Completion criteria

- [x] Every legacy capability classified
- [x] Retained capabilities implemented
- [x] Retained capabilities regression-tested
- [x] Deprecated capabilities covered by negative assertions
- [x] ADRs recorded for score, actors, gateway, representations, diagnostics, invalidation, i18n, WooCommerce boundary
- [ ] **WordPress runtime verification** — ENVIRONMENT BLOCKED
- [ ] **Visual / a11y / RTL verification** — ENVIRONMENT BLOCKED

The last two are why Phase 9 is not APPROVED.
