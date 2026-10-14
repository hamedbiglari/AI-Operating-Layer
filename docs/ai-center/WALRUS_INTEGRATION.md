# Walrus Memory Integration (ADR-091, REQ-AIC-006)

## Status: boundary only — not yet implemented

The Walrus HTTP API contract has not been verified in any accessible environment
(no endpoint, no credentials available). Implementing a client based on documentation
alone would be fake integration. The boundary is defined; the client is deferred.

## Boundary

```python
# app/integrations/memory/walrus.py
def health() -> WalrusHealth        # DISCONNECTED | BLOCKED_EXTERNAL_DEPENDENCY
def namespace_for(org_id) -> str    # server-derived: "org-{uuid}"
def mirror_write(org_id, item) -> bool   # returns False (not configured)
```

## Architecture (when implemented)

```
Merchant AI Operating Layer
    ├── Native Core Memory (canonical)  ← PostgreSQL ai_working_memory
    └── Optional Walrus semantic recall ← mirrors items for semantic search
```

- Namespace = `org-{organization_id}` (server-derived; clients cannot submit one)
- Delegate credentials = server-side only (`WALRUS_API_URL`, `WALRUS_DELEGATE_KEY`)
- If unavailable: system continues on native memory; Walrus is never a single point of failure

## Current runtime behaviour
`GET /ai-center/memory/semantic-backend` → `{ "status": "DISCONNECTED", "canonical_store": "postgresql" }`

## To activate
Set `WALRUS_API_URL` and `WALRUS_DELEGATE_KEY`. The boundary functions will then be
replaced by real HTTP calls once the API contract is verified from official Walrus documentation.
