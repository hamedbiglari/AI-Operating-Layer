# AI Operating Layer — clean build

A consolidated copy of the project, with its test suites and the 2026-10-14 security audit
(`SECURITY_AUDIT.md`). No build artifacts,
dependencies, virtualenvs, database files, or version-control metadata.

## website/

The public static site. Plain HTML, CSS and JS — no build step, no bundler.
Serve the folder with any static file server:

    cd website && python -m http.server 8000

English pages sit at the root; the Persian (fa_IR) mirror is under `fa/`, and
long-form articles are in `blog/` and `fa/blog/`. `assets/` holds the three
stylesheets, two scripts, self-hosted Inter and Vazirmatn woff2 fonts with
their SIL OFL licenses, and the icon set. `sw.js` plus `manifest.webmanifest`
make it installable; `offline.html` is the service-worker fallback.
See `website/README.md` for the full page inventory and deploy notes.

Every page shares one footer: newsletter row, four link columns (one with a "New" chip), and a bottom bar
with copyright, a status indicator and a language selector. The status reads "Website online" while the
site runs on its own; once `site-config.js` points at Cloud Core it asks the public health endpoint and
shows "All systems operational", "Some services degraded" or "Status unavailable" — never a claim it has
not checked. The home page has a dark spotlight promotion section and the hero's knowledge sphere with
its glowing core. Both themes (light and dark) apply to all of it.

## dashboard/

The dashboard prototype: one self-contained `index.html` with every screen,
style and script inlined. No assets to resolve — open it directly in a browser.

- **Uploads** into Cloud Core (documents, keyword lists, Search Console exports) all use one dropzone
  component: drag or browse, size check with a red error row and Retry, a progress bar, then a green
  completed row. The transfer is one function (`AIOLDropzone.transfer`) that can be swapped.
- **Usage** (Payment screen): per-quota meters for prepaid credit, each AI account's monthly spend
  limit and the AI-visibility budget, this month's tokens, and an amber warning card when a quota passes
  the user's alert threshold (saved per user, 50–100 %, default 80 %). Data: `GET /api/v1/billing/usage`.
  Until the dashboard is connected it shows a preview labelled DEMO DATA.

## core/

The FastAPI backend source. `app/` is the application (`main.py` plus the
`api`, `services`, `models`, `schemas`, `security`, `ingestion`,
`integrations`, `ai`, `db`, `core`, `contracts` and `workers` packages).
`migrations/` holds the Alembic environment and 39 ordered revisions.

    cd core
    python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    cp .env.example .env                           # then fill in the values
    alembic upgrade head                           # needs a reachable Postgres
    uvicorn app.main:app --reload

`Dockerfile` builds the same service as an image (production mode, unprivileged user).

Tests: `core/tests/` (pytest; needs PostgreSQL with pgvector and, for the rate-limit tests, Redis):

    cd core && pip install -r requirements.txt
    DATABASE_URL=postgresql+psycopg://aiol:aiol@localhost:5432/aiol alembic upgrade head
    pytest -q

The WordPress plugin's PHP checks: `bash wordpress-plugin/tests/run.sh`.

## tools/

Website build and publishing scripts (Python 3, no dependencies; minifying the script also needs Node):

    python3 -I tools/build_site.py website        # breadcrumbs, llms.txt, site.min.js, asset version
    python3 -I tools/check_seo.py website         # the SEO checklist; exits non-zero on any failure
    python3 -I tools/configure_site.py website --domain https://www.your-domain.com
    python3 -I tools/configure_site.py website --business tools/business.json   # real details only

`business.example.json` shows the fields for LocalBusiness data. See "SEO and publishing checklist" in
`website/README.md`.

## wordpress-plugin/

The WordPress plugin source, installable as-is: drop the folder into
`wp-content/plugins/` and activate. `ai-operating-layer.php` is the entry
point, `includes/` the classes, `admin/` the admin screens, `assets/` the
stylesheets, script and icon paths, and `languages/` the translation
template plus the Persian catalogue. It talks to `core/` over HTTP and keeps
no schema of its own. See `wordpress-plugin/README.md` for configuration.

## Not included

Tests, `__pycache__`, `.venv`, local Postgres data, git history, the visual
harness (byte-identical to `dashboard/index.html`), the `docs/` specification
tree, the canonical `frontend/design-system` sources (the plugin already ships
byte-identical copies in `wordpress-plugin/assets/css/`), and the design-system
sync scripts.
