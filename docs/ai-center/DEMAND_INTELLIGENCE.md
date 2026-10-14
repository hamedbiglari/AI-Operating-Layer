# Demand Intelligence (REQ-DI-001/002/003)

## Status: REGISTERED_OPEN — first-party data exists; external connectors need OAuth

## What exists now (Phase 13, telemetry module)
- Page views, search events, search-demand aggregation
- AI visibility observations (mention / citation / recommendation / product display / click / visit / purchase — kept distinct per Phase 12 design)
- `/api/v1/telemetry/*` routes (page-view list, search-demand terms, access-decision events)

## What REQ-DI-001/002/003 adds (not yet implemented)
- Google Search Console connector (requires OAuth client credentials — external dependency)
- Google Analytics / GA4 connector (same)
- WooCommerce cart / checkout / purchase behaviour feed (pipeline exists via the plugin hook; no explicit behaviour-intelligence model yet)

## Architecture intent
```
First-party sources (Phase 13) → already implemented
External sources (GSC, GA4) → BLOCKED_EXTERNAL_DEPENDENCY
                ↓
Demand Intelligence layer (aggregate)
                ↓
Knowledge gaps / content opportunities / query clusters → Research tasks → Evidence → Knowledge
```

## Human vs AI behaviour distinction
Human behaviour: searches, page views, product views, cart, purchase (first-party, privacy-respecting, aggregated).
AI behaviour: visibility signals from the AI Visibility module — distinct from human behaviour, never merged.

## To activate external connectors
Register a Google OAuth client, configure `GSC_CLIENT_ID / GSC_CLIENT_SECRET`, implement the connector under `app/integrations/demand/`.
