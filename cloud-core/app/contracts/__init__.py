"""
Cross-domain read contracts.

Each module here is OWNED BY the domain it exposes, not by its
consumers. `commerce.py` belongs to the Commerce/Product domain (Phase
7) even though its only consumer today is the Recommendation domain
(Phase 8).

The rule this package exists to enforce: a consumer depends on the
returned read model and nothing else. It never imports another
domain's ORM model, never writes its own `select()` against another
domain's tables, and therefore never has to change when that domain
changes its internal storage - only when the CONTRACT itself changes.

This is deliberately a thin layer of plain dataclasses and functions,
not a repository framework. Section 39 of the Phase 8 brief: "Do NOT
introduce abstractions merely for ceremony."
"""
