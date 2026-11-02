# AIOL — Architecture

The shape of the system, the invariants that hold it together, and where things live. For the current state of
work see `docs/ai-context/AIOL_MEMORY.md`; for open debt see `docs/ai-context/DEBT_REGISTER.md`.

## 1. What AIOL is

AIOL (AI Operating Layer) is an operating layer over an organization's knowledge: it ingests sources and documents,
turns them into evidence, claims and knowledge objects with a traceable provenance, and connects that knowledge to AI
providers, AI agents and the organization's own website. It is multi-tenant, bilingual (English and Persian, with full
right-to-left support) and AI-connected. It is a modular monolith: every phase extends the same codebase, nothing is
deployed as a separate service. AI Core is the source of truth; the WordPress plugin is an adapter, and WooCommerce is
an integration behind it. The primary API is REST; agent interfaces such as MCP build on the same core.

Four components:

| Component | Where | What it is |
|---|---|---|
| Backend ("AI Core") | `cloud-core/app/` | Python, FastAPI, SQLAlchemy, PostgreSQL + pgvector, Redis + Celery |
| Harness | `visual-harness/index.html` | One HTML page: the dashboard, every screen, sample and live |
| Native apps | `apps/` | Tauri 2 clients for Windows, macOS, Android and iOS |
| Deployment | `docker-compose.yml` | The stack for local runs and CI |

## 2. System shape

```
  ┌───────────────────────────┐      ┌──────────────────────────┐
  │ Harness (index.html)      │      │ Native apps (Tauri 2)    │
  │ sample content by default │      │ apps/shared + platform   │
  │ live after Connect        │      │ shells                   │
  └─────────────┬─────────────┘      └────────────┬─────────────┘
                │  REST /api/v1/...                │  REST /api/v1/...
                │  Authorization: Bearer <JWT>     │  native session (refresh)
                │  (token kept in page memory      │
                │   only, never stored)            │
                ▼                                  ▼
  ┌────────────────────────────────────────────────────────────┐
  │ AI Core: FastAPI  (cloud-core/app)                         │
  │   api/v1 routes → services → models (organization-scoped)  │
  └──────┬─────────────────┬───────────────────┬───────────────┘
         │                 │                   │
         ▼                 ▼                   ▼
  ┌─────────────┐   ┌─────────────┐    ┌────────────────────────┐
  │ PostgreSQL  │   │ Redis       │◀──▶│ Celery worker + beat   │
  │ + pgvector  │   │ (broker,    │    │ ingestion, AI jobs,    │
  │             │   │  rate limit)│    │ sweeps, research runs  │
  └─────────────┘   └─────────────┘    └───────────┬────────────┘
                                                   │
                                                   ▼
                                   ┌───────────────────────────────┐
                                   │ External AI providers         │
                                   │ (credentials encrypted with   │
                                   │  AI_CREDENTIAL_KEY, Fernet)   │
                                   └───────────────────────────────┘

  WordPress plugin (wordpress-plugin/) ── machine credentials ──▶ AI Core
```

## 3. Multi-tenancy and auth

**Tenancy.** Every tenant-owned row carries `organization_id`, and every query that reads or writes tenant data
filters by the caller's organization. Foreign keys are mixed. Many tables reference their parent through a
composite foreign key on `(id, organization_id)`, so the database itself refuses a row that points into another
organization; this is how most references to sites, products, installations, users, agents and documents are
built. The original knowledge chain (documents → sources, chunks, evidence, claims, entities, conversations) uses
single-column foreign keys, so for those tables the organization boundary is enforced in the query layer, not by
the database. A test checks
that every table has `organization_id` (or is explicitly exempt).

**Cross-organization access is a 404, never a 403.** `security/tenant.py::get_tenant_scoped_or_404` loads a row by id
and organization together; a row that does not exist and a row that belongs to someone else are indistinguishable to
the caller.

**Authentication.** `security/dependencies.py::get_current_user` decodes the bearer JWT, loads the user, and refuses
an inactive user or an organization that is not active (or pending). The JWT (`security/tokens.py`) carries `sub`
(user id), `org` (organization id), `role`, `iat` and `exp`; the user and organization are re-read on every request,
so a changed status takes effect without waiting for the token to expire. Sign-in is by email code or password;
the native apps use refreshable sessions (`auth_session_service`). Machine clients (the WordPress plugin, adapters)
authenticate with their own installation credentials and scopes (`security/machine_identity.py`).

**Roles** (per organization): `owner`, `admin`, `researcher`, `editor`, `analyst`, `viewer`.

- `ADMIN_ROLES = {owner, admin}` — organization settings, members, access rules, deletes.
- `KNOWLEDGE_EDITOR_ROLES` — who may change knowledge (sources, evidence, claims).
- Routes declare their requirement with `require_roles(...)`; the backend is the authority, the UI only mirrors it.

**Platform administrators** are a separate axis: a platform admin administers the platform across organizations,
not one organization. The grant lives in the `platform_admins` table and is read from the database on every request
by `require_platform_admin` (never from a token claim). `/api/v1/admin/*` is platform-admin only; tenant routes keep
their isolation even for a platform admin. `GET /auth/me` tells the UI whether the caller is one.

## 4. Backend structure

```
cloud-core/
  app/
    api/v1/       routes: parse input, declare auth, call a service, shape the response
    services/     business logic; every query is organization-scoped here
    models/       SQLAlchemy models (enums in models/enums.py)
    schemas/      Pydantic request and response models (the public API contract)
    security/     auth dependencies, tokens, tenant scoping, machine identity, rate limits
    workers/      Celery app, beat schedule and tasks
    ingestion/    document conversion (MarkItDown behind converter.py) and extraction
  migrations/versions/   Alembic, numbered 0001 upward
  tests/                 pytest
```

Routes stay thin; the service owns the query. Public contracts are schemas, never raw ORM objects. A new endpoint
looks like this:

```python
@router.get("/things/{thing_id}", response_model=ThingRead)
def get_thing(
    thing_id: UUID,
    current_user: User = Depends(get_current_user),          # or require_roles(...)
    db: Session = Depends(get_db),
) -> Thing:
    return get_tenant_scoped_or_404(
        db, Thing, thing_id, organization_id=current_user.organization_id, not_found_message="Thing not found"
    )
```

Writes that matter are audit-logged (`services/audit.py::record_audit_log`). Errors use one envelope,
`{"error": {"code", "message"}, "request_id"}` (`core/errors.py`).

## 5. Harness structure

`visual-harness/index.html` is the product's dashboard: one file holding every screen's markup, styles and scripts.

- **Edited directly, never regenerated.** `build.js` is stale; running it would overwrite the page. The file has
  mixed CRLF/LF line endings: an edit must keep each line's own ending, or the diff floods.
- **Sample and live.** Every screen ships designed sample content and works without a backend. After *Connect*
  (an AI Core URL and a token, kept in page memory only), live code mounts over the sample: a screen marked
  `data-live-wired` hides every direct child except `.page-header`, `.breadcrumbs`, `.live-panel` and
  `[data-live-keep]`, so the live body must carry `data-live-keep`.
- **Routing** is by hash: `#screen-<name>`, with parameters after `?` (`#screen-detail?id=<uuid>`). Showing a screen
  fires `aiol:screenchange`; connecting fires `aiol:live`.
- **Registry.** Screens wired through the generic live layer are entries in the `SCREENS` map
  (`'screen-sources': { kind: 'sources', ... }`); on `aiol:live` the `kind` picks the screen function. Some screens
  have their own module and connect themselves.
- **Not-yet-backed design** is hidden with `data-debt-hidden="<debt id>"` (never deleted), so the design and the
  debt register stay in step.
- Every live screen has a browser suite in `visual-harness/e2e/` that mocks AI Core in the page.

A new live screen, in outline:

```js
var SCREENS = { /* ... */ 'screen-things': { kind: 'things', title: 'Things (AI Core)', compact: true } };
// ...dispatch: else if (cfg.kind === 'things') thingsScreen(panel);
function thingsScreen(panel) {
  return visScreen(panel, 'screen-things', function build(body) {
    var p = {}, card = visCard(body, 'Things');            // titles are i18n keys
    p.rows = visTable(card, 'Things, newest first', ['Name', 'Status']);
    return p;
  }, function fetch() {
    return api('/things?limit=50');                         // one call per load
  }, function render(p, page) {
    p.rows.textContent = '';
    page.items.forEach(function (t) { visRow(p.rows, [el('bdi', null, t.name), visBadge(THING_STATUS, t.status)]); });
  }, 'Could not load things ({error}).');
}
```

## 6. i18n (English and Persian)

Persian is a first-class language, not a translation pass. This is the invariant most easily broken without
noticing, because a reversed or untranslated string still *looks* fine in an editor.

**How text is translated.** English is the key. The Persian table `FA` (end of `index.html`) maps an English string
to its Persian text. Two paths use it:

- Static text: a watcher translates text nodes whose content is an `FA` key, under the roots it observes.
- Runtime text: `AIOL_I18N.set(node, 'English template {n|item|items}', args)` stores the template on the node and
  re-renders it when the language changes. `{n}` formats numbers; `{d}` with `{ date, style }` formats dates;
  `{x|one|other}` adds the English plural; any other argument is inserted direction-isolated.

**Numbers and dates** use `Intl` for the current language: `fa-IR` gives Persian digits, Persian separators and the
Solar Hijri calendar. Backend values stay ISO 8601 / UTC.

**What is never translated.** The Persian layer skips `bdi`, `code`, `input`, `textarea`, `select`, `.identifier`,
`script`, `style` and `svg`. Data (names, emails, URLs, identifiers, server text) goes in `<bdi>` or `.identifier`.
Option text inside a `<select>` is set with `AIOL_I18N.set` or stays as written.

**Rules that keep it correct:**

- **Persian is built from code points, never typed.** Bidirectional rendering reverses text in chat and in some
  editors; the source of truth is the code points, and tests build their Persian expectations with
  `String.fromCharCode(...)` so the test files stay ASCII.
- **No identity entries.** An `FA` value equal to its English key makes the watcher rewrite the node forever (an
  infinite mutation loop). Mark the text `.identifier` instead.
- **No manual isolation around arguments.** `arg()` already wraps every argument in FSI/PDI; an `FA` string never adds
  its own around `{arg}`. Literal protocol tokens (`https://`, `HTTP 500`) are wrapped where they appear.
- **Leading punctuation.** A translation starting with a Persian comma, semicolon or question mark gets no space
  prepended (`keepSpace`).
- **Templates are literals.** The coverage tool reads the first string literal inside `AIOL_I18N.set(...)` as the
  template, so create a node first and pass it; never nest `el('x', 'class')` inside the call.

**The two gates** (both must exit 0 before a UI commit):

- `node visual-harness/check-persian.js` — every Persian word in `i18n-glossary.md` must be in its `KNOWN` list
  (written in hex so it cannot be reversed), and no word in `FA` may be a known word reversed.
- `node visual-harness/i18n-coverage.js --require <screens>` — each required screen's visible static text is 100%
  translated (it skips `.identifier`, `<bdi>` and `[data-debt-hidden]`), and every literal `AIOL_I18N.set` template
  anywhere has an `FA` entry.

**Adding a string — checklist:**

1. Write the English in code (`AIOL_I18N.set` for runtime text).
2. Add the `FA` entry, generated from code points; reuse the glossary's terms.
3. Add the pair to `i18n-glossary.md` under the change's section.
4. Add any new Persian word to `KNOWN` in `check-persian.js` (hex), after checking its letter order.
5. Add a Persian check to the screen's e2e suite.
6. Run both gates and the screen's suite.

## 7. Native apps

- `apps/shared/` — the shared client source (UI, API client, export tooling) and its tests.
- `apps/windows/`, `apps/macos/`, `apps/android/`, `apps/ios/` — per-platform shells, each with `src-tauri/`
  (Rust, `tauri.conf.json`, `Cargo.toml`, `Cargo.lock`).
- Built per platform with `npm run tauri build` (Windows needs the MSVC Build Tools and Windows SDK).
- Their CI is separate: `.github/workflows/clients.yml`; the backend and harness run in `ci.yml`.
- Desktop sign-in uses native sessions; updates are signed packages (no unsigned in-app updater).

## 8. Data flow — the Sources list

1. The user opens `#screen-sources` while connected; the `SCREENS` entry (`kind: 'sources'`) has wired `sourcesList`.
2. It sends one request: `GET /api/v1/sources/overview?sort=updated&limit=50&offset=0` (plus any search, type,
   status or archive filter), with the bearer token.
3. `get_current_user` decodes the token, re-reads the user and organization, and refuses an inactive one.
4. The route calls `source_overview_service.get_overview`, which runs a constant number of queries for the whole
   page: grouped document and evidence counts joined into the page query, the total, and the per-status counts —
   all filtered by `organization_id`.
5. The response is a `SourceOverviewPage`: rows with their counts, `derived_status` and last activity, plus
   `counts_by_status` for the filter panel.
6. The harness renders the rows (titles in `<bdi>`, status badges and dates through `AIOL_I18N.set`), so switching
   language re-renders them without another request.

## 9. Key invariants

The numbered rules live in `docs/ai-context/AIOL_MEMORY.md` §2; these are the ones the code depends on.

- **No schema change without the owner's approval** (Rule 6). Migrations are additive and reversible.
- **Every tenant-owned table has `organization_id`**, and cross-organization reads answer 404 (§3).
- **Lists are one call, a constant number of queries** (Rule 17): no request per row from the UI, no query per row on
  the server. Related data comes from a grouped subquery or a batch endpoint.
- **Counts, not scores** (ADR-024): the UI shows what was measured; no invented composite ratings.
- **A migration must upgrade, downgrade and upgrade again on a fresh database.** Run
  `scripts/check-migrations-fresh.ps1`; CI's fresh database is the final word. An enum value added in a migration
  cannot be used in the same transaction.
- **Persian rules** (§6): code points only; no identity entries; no manual FSI/PDI around arguments (Rule 15);
  `keepSpace` before Persian punctuation (Rule 13).
- **Both i18n gates exit 0 before every UI commit** (Rule 10).
- **New tests fail before the fix and pass after it** (Rule 5): prove it by running them without the change.
- **The harness is edited, never regenerated**, and keeps each line's ending.

## 10. Testing

- **Backend:** pytest in `cloud-core/tests`, against PostgreSQL (`DATABASE_URL=postgresql+psycopg://aiol:...`; the
  `aiol_postgres` container locally). Each test runs inside a transaction that is rolled back. CI enforces 92%
  coverage.
- **Harness:** browser suites in `visual-harness/e2e/*.js` (Playwright, AI Core mocked in the page, every request
  recorded), plus the static gates (`check-persian.js`, `i18n-coverage.js`, `check-source-chars.js`).
- **Native apps:** unit and e2e tests in `apps/shared`, run by the client workflow.
- **CI is authoritative** for the full backend suite (Rule 21): locally, run the suites a change touches.
- **Real providers** are never called in CI; `visual-harness/e2e/real-keys.js` is a manual run
  (`docs/e2e-real-keys.md`).

## 11. Deployment

`docker-compose.yml` runs the stack:

| Service | Role |
|---|---|
| `postgres` | PostgreSQL with pgvector (bound to localhost) |
| `redis` | Celery broker and rate-limit counters (bound to localhost) |
| `migrate` | one-shot `alembic upgrade head` before the API starts |
| `cloud-core` | the FastAPI app |
| `celery-worker` | ingestion, AI jobs, research runs |
| `celery-beat` | periodic sweeps (stalled jobs, recovery, retention) |
| `visual-harness` | the harness, served by nginx |

Settings come from the environment (every one is listed in `.env.example`). Two matter for data safety:
`AIOL_SOURCE_STORE`, where uploaded originals are kept, and `AI_CREDENTIAL_KEY`, the Fernet key that encrypts
provider credentials at rest — keep it stable, or stored credentials can no longer be decrypted. The API image starts
in production mode and refuses to boot while `SECRET_KEY` or the database password hold development defaults; set
`APP_ENV=development` for local work.

## 12. Where to find things

| What | Where |
|---|---|
| Current state, rules, history | `docs/ai-context/AIOL_MEMORY.md` |
| Debt register (what is not built yet, and why) | `docs/ai-context/DEBT_REGISTER.md` |
| Architecture decisions (ADRs) | `docs/DECISIONS.md` |
| Master specification | `docs/master-spec/MASTER_SPEC.md` |
| Persian glossary | `visual-harness/i18n-glossary.md` |
| API and database notes | `docs/api.md`, `docs/database.md` |
| Development setup | `docs/development.md` |
| Migrations | `cloud-core/migrations/versions/` |
| Fresh-database migration check | `scripts/check-migrations-fresh.ps1` |
| Real-key end-to-end run | `scripts/start-real-e2e.ps1`, `docs/e2e-real-keys.md` |
| CI | `.github/workflows/ci.yml` (backend + harness), `clients.yml` (apps) |

## 13. What this document does not cover

- Work in progress and what comes next — `docs/ai-context/AIOL_MEMORY.md`.
- Open debt and its status — `docs/ai-context/DEBT_REGISTER.md`.
- Setting up a development environment — `docs/development.md` and the top-level `README.md`.
- Individual decisions and their reasoning — `docs/DECISIONS.md`.
