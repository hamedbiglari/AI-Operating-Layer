# Final Existing-Owner Audit (2026-09-25)

## Classification key
IMPLEMENTED_BACKEND = DB + API + service exist and are tested
PRODUCTION_UI_LIVE = backend-connected UI screen (live, no sample data)
VISUAL_HARNESS_ONLY = exists in visual-harness/index.html only
API_ONLY = route exists, no UI wired
DESIGNED_ONLY = architecture documented, no code
MISSING = not started
EXTERNAL_DEPENDENCY_BLOCKED = implementation ready but external credential required
VISUAL_HARNESS_SAMPLE = harness screen exists with sample/fixture data

---

## AI Center

| Feature | Status | Evidence |
|---|---|---|
| Providers (register, list, test) | IMPLEMENTED_BACKEND | api/v1/ai_center.py; test_ai_center.py |
| Accounts (multi-account, credentials) | IMPLEMENTED_BACKEND | credentials Fernet-encrypted; tested |
| Models registry | IMPLEMENTED_BACKEND | ai_models table; not hard-coded |
| Routing (6 modes, explainable) | IMPLEMENTED_BACKEND | ai_routing_policies; 6 modes tested |
| Jobs + checkpoint + handoff | IMPLEMENTED_BACKEND | ai_jobs, ai_job_items, ai_working_memory |
| Shared AI Working Memory | IMPLEMENTED_BACKEND | ai_working_memory table; versioned |
| Walrus boundary | IMPLEMENTED_BACKEND | app/integrations/memory/walrus.py; honest DISCONNECTED |
| AI Catalog / Discovery Registry | IMPLEMENTED_BACKEND | ai_discovery_entries; 114 entries; API |
| Keyword Workspace | IMPLEMENTED_BACKEND | knowledge_keywords; CSV/Excel/TXT/JSON/manual |
| Keyword → Research Task (REQ-KW-003) | IMPLEMENTED_BACKEND | last_research_task_id link |
| **AI Center UI (all the above in Dashboard)** | **VISUAL_HARNESS_ONLY** | visual-harness/index.html #screen-ai-center |
| **AI Catalog as first-class nav item** | **MISSING** | Buried under "Discovery" tab in AI Center; owner explicitly said "لیست AI را ندیدم" |
| **Shared Memory configuration screen** | **MISSING** | Status shown in "Jobs & memory" tab only; owner explicitly said "قسمت اتصال و انتخاب حافظه مرکزی مشترک را ندیدم" |
| **Background Processing policy** | **MISSING** | No DB model, no API, no UI |
| **Agent Network / Orchestration** | **MISSING** | No DB models, no API, no UI |
| **REQ-KW-004 (full keyword→content trace)** | **MISSING** | Link stops at research_task_id; source→evidence→knowledge→content not traced |

## Settings

| Feature | Status | Evidence |
|---|---|---|
| Org name (Cloud Core live) | PRODUCTION_UI_LIVE | Settings screen data-live-wired; PATCH /organizations/me verified |
| Profile & verification | VISUAL_HARNESS_SAMPLE | profile-slot-me; sample data only |
| Appearance / Language / Theme | VISUAL_HARNESS_SAMPLE | No backend persistence for locale/theme |
| **AI Preferences** | **MISSING** | No screen; no backend |
| **Background Processing settings** | **MISSING** | No screen; no backend |
| **Shared Memory settings** | **MISSING** | No screen; no backend |
| **Routing Preferences** | **MISSING** | No settings screen; AI Center has routing but no settings integration |

## Live-wired screens (production UI)
1. Dashboard overview (Cloud Core stats)
2. Knowledge list + detail
3. Sources
4. Processing jobs
5. AI Visibility projects
6. Products + offers
7. Settings → Organization name
8. AI executions (full live screen)
9. AI Center → Providers & accounts, Routing, Jobs & memory, Discovery (VISUAL_HARNESS_ONLY in a single screen)

## Gap summary
- Agent Network: MISSING (new domain; ADR needed)
- Background Processing Policy: MISSING (new domain; DB + API + UI)
- AI Catalog as top-level nav: MISSING (UX gap; data exists, not surfaced)
- Shared Memory control: MISSING (settings + AI Center inspection screen)
- Keyword → published content traceability (REQ-KW-004): MISSING
- REQ-DI-001/002/003: EXTERNAL_DEPENDENCY_BLOCKED (no OAuth credentials)
