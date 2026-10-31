# AIOL MEMORY — single source of truth

<!-- This file is the only memory. Any other handoff is stale.
     AUTHORITATIVE ONLY IF `sha:` below equals the last commit whose
     subject does NOT start with "docs". Any commit starting with "docs"
     (docs:, docs(i18n):, docs(debt):, docs: AIOL_MEMORY, ...) does NOT
     move `sha:`. All other commits do.
     Anchor command:
       git log --oneline -1 --grep='^docs' --invert-grep | cut -c1-7
-->

## 0. How to use this file (read first)

You are the planning/review assistant. You do NOT see the code. You have
zero memory between sessions. This file IS your memory.

On load:
1. Trust this file. Do NOT ask the user for git output directly.
2. Your FIRST reply is a short drift-check prompt for the user to paste
   into Claude Code. Output ONLY this text, nothing else:

       Run and report exactly these four commands, in order, with their
       raw output, no commentary:
         git rev-parse HEAD
         git log --oneline -1 --grep='^docs' --invert-grep | cut -c1-7
         git status --short
         git log --oneline -5

       Label the second output "ANCHOR:".

3. When the user pastes Claude Code's reply back, extract the line
   labeled "ANCHOR:" and compare it to the `sha:` value in §3.
   - ANCHOR equals `sha:` → say "state in sync", give a 2–3 sentence
     summary, wait for "go".
   - ANCHOR differs from `sha:` → say "STATE DRIFT", list:
     (a) the anchor value the repo reports,
     (b) the sha: value in §3,
     (c) any unexpected entries in `git status --short`,
     then wait for the user's decision. Do not guess, do not proceed.
   Note: HEAD may be a docs commit (docs: AIOL_MEMORY vN ...). That is
   normal and is NOT drift. Only the ANCHOR matters for the comparison.

4. Only after "go", proceed per §6.
5. Never say "I remember". Never propose work before drift check completes.

Drift anchor rule (this is what §3's `sha:` refers to):
  Any commit whose subject starts with "docs" does NOT move the anchor.
  Every other commit DOES move the anchor.
  Anchor is computed with:
    git log --oneline -1 --grep='^docs' --invert-grep | cut -c1-7

End of session: the user invokes the end ritual. Regenerate this ENTIRE
file from scratch (do not diff). Output only the file content.

## 1. Project identity

- Repo: C:\Users\Hamed\Downloads\1- AI-Operating-Layer\graphify-src\02-core-tool-full-repo
- Branch: v5-implementation
- Stack: FastAPI backend (cloud-core/app) + single-page HTML harness
  (visual-harness/index.html, 13,377 lines, edited directly)
- Goal: wire 52 mock screens to real backend, translate to Persian,
  lock translation coverage in CI.
- Language: Persian for explanation, English for code/commits.
- Environment constraints: see §10.4.

## 2. Working rules (do NOT re-derive, do NOT relax)

### Process
1. CI-first: diff → user approves → commit → push → CI green → next.
   Never commit before showing the diff.
2. Small shippable commits: one concept each. Backend commit before the
   frontend that consumes it.
3. No force-push. Amend before push only.
4. Long diffs truncate in chat. Ask Claude Code for ~30-line snippets.
5. Test rule: new tests must FAIL pre-fix and PASS post-fix. Prove by
   stashing the fix, running, restoring, running again.
6. No schema change without asking. No touching billing/auth/payments.
7. Deferred features → docs/ai-context/DEBT_REGISTER.md
   {name, description, status: OPEN, category}. Never in code comments.
8. This file updated ONLY at end-of-session, as its own docs commit.

### Persian / i18n
9. Build Persian strings from explicit codepoints (chr() /
   String.fromCharCode()). Verify with check-persian.js round-trip.
   Never trust chat display — bidi reverses.
10. Two-check gate before any UI commit:
    node visual-harness/check-persian.js → exit 0
    node visual-harness/i18n-coverage.js --require <screens> → 0, exit 0
11. i18n-coverage.js has TWO checks: (a) --require per-screen 100%;
    (b) every literal AIOL_I18N.set template must have an FA entry,
    ACROSS ALL SCREENS. English-first partial wiring fails CI.
12. AIOL_I18N.set is used for fixed strings AND templates with runtime
    values. Use it whenever the string must be translated and the
    observer cannot reach the node (e.g. detached elements, values set
    after mount). For static node text the observer can see, plain
    textContent is sufficient. Do not treat the two paths as exclusive.
13. keepSpace() must not prepend source-leading space when translation
    starts with Persian comma/semicolon/question (، ؛ ؟).
14. .identifier class skipped by i18n-coverage.js (application/pdf, etc.
    are identifiers, not UI text).
15. Auto-isolation: no FA string combines manual FSI/PDI with {arg}
    templates. Literal HTTP codes wrap in \u2068…\u2069; template args
    get isolation from arg() automatically.

### Sample vs Live
16. Sample-mode content is preserved; live mode mounts over it
    (CSS body[data-live="on"] or data-live-wired). Sample re-insertion
    JS must early-return when body.dataset.live === 'on'.

### Backend / tests
17. Overview aggregates follow /dashboard/summary + /knowledge/overview
    pattern: single batch endpoint, no per-row calls.
18. Local backend tests: DATABASE_URL=postgresql+psycopg://aiol:aiol_dev_password@localhost:5432/aiol
    (default hostname `postgres` only resolves in Docker Compose).
19. For automated tests hitting Postgres locally, start only aiol_postgres
    container (not full compose).
20. Long test commands: append --durations=20 and PowerShell beep for
    automatic audible completion.
21. CI is authoritative for full backend suites (local Windows is slow
    and memory-heavy). CI uses pgvector/pgvector:pg16.

## 3. Repository state (verifiable)

- sha (last non-docs commit): 75e09ef
- branch: v5-implementation
- working_tree: clean
- last_ci: in_progress @ 75e09ef (8A, 8C, 8D). 913c790 (8A backend) was pushed
  with it and is not built on its own; the run on 75e09ef is the first full
  backend suite for it (the local full run hung on Windows and was
  stopped; test_knowledge_gaps.py passed 7/7 locally).
- last code commit: "feat(knowledge): live gap, matrix, and coverage
  screens (8A, 8C, 8D)" @ 75e09ef
- last feature commit: "feat(knowledge): live gap, matrix, and coverage
  screens (8A, 8C, 8D)" @ 75e09ef
- last fix commit: "fix(processing): cast to text in 0047 backfill
  (PostgreSQL UnsafeNewEnumValueUsage)" @ f32a80a

## 4. Completed steps (compact)

- Step 4 — Dashboard live (stat cards, /dashboard/summary). ADR-024 respected.
- Step 5 — Foundation: glossary, i18n core + Jalali, coverage scanner,
  source-char scanner. All in CI.
- Step 6 — Knowledge screen: live, bilingual, 106 browser checks,
  CI-locked 100%. Backend /knowledge/overview.
- Step 7A — Sources list: live, bilingual, 64 browser checks, CI-locked
  100%. Backend /sources/overview with counts + derived_status.
  Sub-commits 7A1..7A4a.
- Step 7B — Source detail (#screen-detail), CLOSED @ a9839dd:
  - 7B1 @ d555048 — ?id= on GET /sources/overview: 0/1 row, 404 for
    unknown/cross-org, list filters ignored when id is present.
  - 7B2a @ dc046fa (docs) — Source detail glossary, 34 rows, 28 KNOWN
    words; Reprocess has its own locked term, Retry keeps its own.
  - 7B2b-1 @ 71b9822 — 11 V5-source-detail-* debt rows; the 6 mock tabs
    hidden with data-debt-hidden (markup kept).
  - 7B2b-2 @ d4e1192 — live header from /sources/overview?id=; role read
    once per connection from GET /auth/me; no-id / 404 / 422 / network
    states; Sources list Open links carry ?id=.
  - 7B2b-3a @ 9eef37d — backend: /sources/{id}/documents rows are
    DocumentWithConversion (current_conversion {id, status,
    needs_review}; no `content`). No migration.
  - 7B2b-3b @ cff4166 — documents card: Status (extraction) and
    Conversion columns, needs-review badge, Sources-style pager.
  - 7B2b-4 @ 06d315c — per-row text preview (GET /documents/{id}/markdown
    as text, <pre> textContent, read once); Reprocess for owner / admin /
    researcher / editor via window.confirm + POST; list re-read after
    success; a 403 keeps the button.
  - 7B2c-1 @ 757128d (docs) — sample glossary: "Source detail" heading +
    18 sample rows, 26 KNOWN words.
  - 7B2c-2 @ a9839dd — i18n-coverage.js skips [data-debt-hidden] (D6);
    6 sample debt items hidden; 5 identifiers wrapped; empty-state
    heading "Source detail"; screen-detail added to the CI --require.
- Step 7C — Processing, COMPLETE @ 6474e60:
  - 7C-1 @ 522c7f3 — GET /documents/{id}/processing.
  - 7C-2 @ b13d7cc — sync_jobs.document_id column + backfill with EXISTS
    guard + org-match. Migration 0047.
  - fix 0047 @ f32a80a — WHERE job_type::text = 'document_ingestion'
    because 0014 adds the enum value in the same transaction and
    PostgreSQL raises UnsafeNewEnumValueUsage.
  - 7C-3 @ b6d98f4 — sync_job_stages table + SyncJobStageKey /
    SyncJobStageState enums + organization_id (Decision A). Migration 0048.
  - 7C-4 @ 16bb9d1 — emit stage events from ingestion behind
    AIOL_EMIT_STAGE_EVENTS (default false).
    D15: retroactive upload/security for initial uploads only; default
    is_initial=False, so only documents.py passes True.
    D16: reset_run in claim; commit-before-pipeline makes active rows
    visible mid-run; fail_active in fail() shares the SyncJob-failure
    commit.
    D17: FAILED/UNSUPPORTED -> conversion=failed + structure/ocr=
    NOT_TRACKED with detail "not run (conversion failed)"; EMPTY ->
    conversion=failed "no usable text" + structure/ocr=done.
    D18: reclaim_stalled broken; debt row V5-processing-stale-sweeper.
    D19: URL jobs out of scope; debt row
    V5-processing-url-jobs-stage-tracking.
    R2: redundant CI flag-on step removed. R3: pluralized "1 table" /
    "N tables", "1 OCR block" / "N OCR blocks".
    7 tests: flag-off guard, happy path, crashed run,
    FAILED+UNSUPPORTED, EMPTY, retry, flag turned off after upload.
  - 7C-5 @ 62768d7 — extend GET /documents/{id}/processing with
    job: JobRead | None (id, status, attempts, created_at, started_at,
    completed_at) and merge stage-events.
    D20: URL jobs (document_id NULL) and no-job docs -> job=None.
    D21: latest SyncJob by created_at DESC; semantics = "latest
    attempt".
    D22: format_count(n, singular, plural) extracted from
    stage_events._count, imported by processing_service ("1 table" /
    "N tables", "1 OCR block" / "N OCR blocks").
    D26: upload/security rows win when present (Section 4 was right);
    reprocess/URL naturally derived.
    11 tests (T-A..T-H, T-J, T-K + pluralization); stash proof: 11 fail
    pre-fix. No migration.
  - Test suite: test_7c_end_to_end.py @ 1191934 — scenarios A-J cover
    real flows (upload, reprocess, URL, cross-org, idempotency).
    10 tests, all pass. Validates 7C-1..7C-5 end-to-end.
  - 7C-6a @ c10fd28 (docs) — Processing screen glossary, 34 rows,
    36 KNOWN words.
  - 7C-6b @ 27b8ed7 — ProcessingRead gains document_title and mime_type
    from the already-loaded Document (no extra query).
  - 7C-6a2 @ 128f465 (docs) — 6 sample rows; screen renamed "Document
    processing" because the FA key "Processing" is the status.
  - 7C-6c @ 6474e60 — frontend for #screen-processing: live processing
    screen, entry point link from Source detail, full FA dictionary,
    mock alignment, Playwright test, --require gate. Note: found and
    fixed an infinite mutation loop caused by an identity FA mapping
    ("OCR": "OCR").
- Step 7D (Provenance):
  - 7D-1 @ 5caa754 — backend GET /knowledge/{id}/provenance
    (ProvenanceRead): one page of claims (limit/offset) with their
    claim_evidence links, plus evidence/sources/documents maps keyed by
    id (Rule 17: at most 6 queries, constant in claims/links). Claim
    carries predicate, object_value, joined text, status,
    evidence_strength; links carry link_id. Evidence has basis and
    subject_tested; documents have converter_version from the current
    conversion. total_claims = all claims; total_evidence = distinct
    evidence in this page. 4 tests (query count, happy path,
    pagination, cross-org 404). No migration.
  - 7D-2 @ 2d9d56c — live #screen-provenance?id= (kind 'provenance',
    provenanceScreen()): one call with limit=200 and a "Claims shown:
    N of total" line; each claim a .trail--fan card; remove link via
    confirm + DELETE /claim-evidence/{link_id} + reload, editor roles
    only, 403 keeps the button. EDIT_ROLES lifted to module scope;
    /auth/me read once per connection (connectionRole()), shared with
    Source detail. 62 FA entries + glossary section, 67 KNOWN words,
    allowlist pair 13/31 (both numbers). e2e/provenance.js (23
    checks); --require adds screen-provenance.
- 7E @ 9691372 — live #screen-add (kind 'add', addSourceScreen()):
  source picker from GET /sources/overview?limit=100 (read when the
  screen is shown, not on every connect); Document card -> POST
  /documents/upload (multipart, api() opts.form); Web page card -> POST
  /documents/ingest-url; success opens #screen-detail?id=<picked
  source> (neither reply carries a source id). Mock: Dataset and Site
  article cards removed; Research and Supplier document hidden
  (data-debt-hidden, no FA rows, per D6). Old #live-add-source panel
  (POST /sources) kept. 18 FA entries + glossary section, 9 KNOWN
  words. e2e/add-source.js (19 checks); --require adds screen-add.
- Step 8 (partial: 8A, 8C, 8D; 8B Knowledge detail skipped for now):
  - 8A backend @ 913c790 — KnowledgeGapRead.knowledge_object_name
    (model property; the gap list loads the object in one joined
    query, no N+1). 2 tests: name on every gap read; no per-row
    knowledge_objects lookup (fails without the join).
  - 8A/8C/8D frontend @ 75e09ef — live #screen-gap (kind 'gap',
    gapScreen()): ?id= -> GET /knowledge-gaps/{id} + GET
    /knowledge/{object}/gaps (2 calls, other open gaps as links); no
    id -> GET /knowledge-gaps?status=open (1 call, object names). It
    replaces the generic gaps table (its status filter is gone).
    "What has already been checked" hidden (V5-gap-history). Matrix
    and Coverage get data-live-wired; their 22 static strings
    translated (47 FA entries in all with the gap screen; 63 KNOWN
    words). V5-matrix-coverage-runtime-fa OPEN. e2e/gap.js (19) +
    e2e/matrix-coverage.js (13) = 32 checks; --require adds
    screen-matrix,screen-coverage.
- Theme toggle: V5-theme-toggle-ui CLOSED @ fdc7cd7 (toolbar toggle
  repaired, WAI-ARIA toggle-button pattern, e2e/theme-toggle.js).
- Debt state: V5-topbar-lang-save-bug OPEN (#topbar-lang never fires
  change on #pick-lang). V5-source-detail-empty-a11y-name CLOSED
  (Step 7B2c-2). 7B source-detail debt: 11 rows from 7B2b-1 plus
  V5-source-detail-more-actions from 7B2c-2, all OPEN.
- Debt row V5-migration-fresh-db-local-check added @ f32a80a.
- CI now runs i18n-coverage.js --require
  screen-knowledge,screen-sources,screen-detail,screen-processing,screen-provenance,screen-add,screen-matrix,screen-coverage
  and 13 browser suites.

## 5. In progress — next step

- Step 8 is partially complete: 8A, 8C, 8D done @ 75e09ef (see §4).
- Next up: Step 8B (Knowledge detail: the 4 sample pages need a
  template; scope rule 4 requires listing what each page would lose
  and getting confirmation first) OR Step 9 (AI). Propose which one at
  the start of the next session.
- Debt rows added in 8A/8C/8D, both OPEN: V5-gap-history,
  V5-matrix-coverage-runtime-fa.
- Debt rows added in 7E, all OPEN: V5-add-source-dataset,
  V5-add-source-site-article, V5-add-source-research,
  V5-add-source-supplier, V5-add-source-ui-merge (old "Add a source to
  Cloud Core" panel overlaps the Web page card and has no Persian).
- Debt: V5-knowledge-provenance-link OPEN — nothing links to
  #screen-provenance?id= yet (no entry point from Knowledge), although
  the no-id message says "Open one from Knowledge". Not yet written to
  DEBT_REGISTER.md.

## 6. Next action

State in sync → user says "go" → send the next step investigation prompt.

Case A — anchor mismatch (STATE DRIFT): stop, report, wait.
Case B — user says "go": send the next step investigation prompt.
Case C — anything CI-red: paste log, fix before any new work.

## 7. Open decisions (blocking)

(none currently)

## 8. Preferences

- Persian speaker; Windows PowerShell.
- User runs Claude Code CLI separately. You are planning/review only.
- Wants explicit "decision needed" lists over assumptions.
- Commits only after explicit approval.
- No "waiting for CI" filler — report progress only.
- Prefers ~30-line snippets over full diffs.
- Long test commands: append --durations=20 + PowerShell beep.
- GitHub API works without a token in this setup; user checks UI
  manually when needed.

## 9. Changelog

- v1 @ 97325af — created from a fresh chat. 7B1 in-progress captured.
- v2 @ 97325af — §0 rewritten: drift check offloaded to Claude Code.
  Fixed §1/§3/§5/§8 factual errors.
- v3 @ 97325af — drift-check mechanics: unify to ^docs rule; drift prompt
  asks for anchor directly; §0 step 3 compares ANCHOR not HEAD.
- v4 @ 8072ead — 7B1 and DEBT theme-toggle committed. §3/§4/§5 updated.
  §10 added: merged history from two prior sessions. §2 expanded from 10
  to 21 rules. Anchor now 8072ead.
- v4a @ 8072ead — fixes on top of v4 before its first commit:
  CI status, Reprocess roles (backend-authoritative), debt count 8→11
  (adds Artifacts/Evidence/Provenance tabs), hidden-tabs expanded to 6,
  §2 rule 12 reworded to match code. Anchor unchanged.
- v4b @ 8072ead — three consistency fixes before v5: debt count unified
  to 11, §6 prompt item 7 lists all 6 hidden tabs, Artifacts rationale
  corrected (backend exists; hidden for scope). Anchor unchanged.
- v5 @ a9839dd — session closed Step 7B (7B2a, 7B2b-1..4, 7B2c-1/2) and
  the V5-theme-toggle-ui repair; §3/§4/§5/§6 rewritten; Step 7C is next.
  CI on a9839dd was still running when this was written. Anchor now a9839dd.
- v6 @ b6d98f4 — 7C-1, 7C-2, fix 0047, 7C-3 committed. New lessons
  recorded in §10.2.
- v7 @ 16bb9d1 — 7C-4 shipped (flag-gated stage events, D15-D19).
  Two debt rows added. 7 tests. CI green.
- v8 @ 62768d7 — 7C-5 shipped (job object + merge, 11 tests).
  D20/D21/D22/D26 documented.
- v9 @ 1191934 — 7C end-to-end suite added. 7C-5 complete. Ready for
  7C-6.
- v10 @ 6474e60 — 7C-6c shipped. Step 7C is complete. v9's stale
  "in_progress" is corrected to green.
- v11 @ 2d9d56c — 7D-1 (5caa754) and 7D-2 (2d9d56c) shipped. Step 7D is
  complete; 7E (Add source) is next. Debt V5-knowledge-provenance-link
  noted.
- v12 @ 9691372 — 7E shipped (live Add source: upload + URL cards).
  Step 7E is complete; Step 8 is next. Five V5-add-source-* debt rows.
- v13 @ 75e09ef — 8A, 8C, 8D shipped (backend 913c790). Gap, Matrix and
  Coverage screens are now live. 8B remains.

## 10. Historical context (from two prior sessions)

Merged from extractions of chat #1 (older) and chat #2 (newer).
Where they disagreed, chat #2 won. Contains ONLY knowledge that cannot
be re-derived from repo, git log, or current code.

### 10.1 Historical locked decisions (done, not active)

- ADR-024: no invented composite scores. UI shows discrete counts.
- "Needs human review" main number = review.conversions + review.claims_conflicting,
  note "X conversions + Y claims in conflict".
- Live-mode review card loses its href (waiting-on-person panel hidden).
- Persian translation for dynamic summary notes: regex extended for
  multiple $n captures, Persian digits, ٬ thousands separator.
- Pin CI runner ubuntu-24.04 (ubuntu-latest migration began 2026-10-19).
- CI upload storage: AIOL_SOURCE_STORE=${{ runner.temp }}/aiol-sources
  at step level (runner ctx rejected at job level).
- Coverage gate raised to 92% (observed 93.28% left ~1.28 margin).
- checkout/setup-python/upload-artifact @v7 (v5/v6 still Node 20).
- asyncio_default_fixture_loop_scope = function in cloud-core/pytest.ini.
- Language/theme pickers track user-touched during prefs load; late
  saved prefs don't overwrite.
- .gitignore: cloud-core/.coverage, cloud-core/coverage.xml, .impeccable/.
- Glossary finalized: Sources 20+ rows (272 words via check-persian),
  Knowledge 30 rows. Terms: پرونده دانش، تعارض، شاهد/شواهد، منبع، سند،
  تبدیل سند، منشأ، نسخه، شکاف دانش، ارزیابی تحریریه، حالت نمایش.
- Sort labels direction-explicit: "Most claims" / "Most evidence" (7A3b).
- 11 debt entries for 7B dropped elements: Archive, Delete, version badge,
  Knowledge tab, Claims tab, History tab, Artifacts tab, Evidence tab,
  Provenance tab, research projects, gaps affected.
- Add source = 2 cards only (Upload, URL). Dataset & Site article removed
  (no backend ingestion), debt entries.
- Users toolbar "View" aria-label stays English (debt V5-users-view-aria-label).

### 10.2 Gotchas and lessons learned

Bidi / codepoints:
- Persian codepoints in chat display reverse or truncate (02634, 0632F
  malformed). Always verify via Python byte read or check-persian.js.
- Intl.NumberFormat for Persian digits requires Number, not string.
- Arabic digits for HTTP codes wrong — protocol identifiers use Latin
  digits inside <bdi>.
- Arrow-only sort labels (↑/↓) ambiguous in RTL; screen readers lose
  A–Z. Use «نام (الف تا ی)» / «نام (ی تا الف)».

Shell / PowerShell:
- grep -c $'\r' in "$(…)" doesn't expand \r; matches every line. Use
  Python byte-count for CR/LF.
- PowerShell pipe into git commit -F adds BOM to subject. Use bash
  heredoc; byte-check subject post-commit.

SQLAlchemy / models:
- __table__.columns vs inspect(Model).column_attrs differ
  (metadata_ vs metadata). Use column_attrs for Python attribute names.
- hasattr(Model, col) true for relationships/properties which ORDER BY
  crashes on. Systemic test uses column_attrs + per-model parametrization.

Harness / Playwright:
- index.html has mixed CRLF/LF line endings. Edits must preserve per-line
  EOL, else whole-file diff noise.
- Playwright local 1.64.0-alpha, CI pins 1.56.1. Do not re-install.
- Playwright MCP profile locked / Chrome fails. Use bundled headless
  Chromium scripts.
- file:// origin null breaks CORS. Serve harness over HTTP for live tests.

CI:
- CI PermissionError /var/lib/aiol came from default
  AIOL_SOURCE_STORE=/var/lib/aiol/sources. Runner can't write there.
- Only graphify-src/02-core-tool-full-repo/.github/workflows/ci.yml is
  real CI; root has no .github.
- Full CI ~12 min. Local full suite 15–30+ min, memory-tight.
- GitHub Actions logs/artifacts require login; gh not installed. Need
  user to paste logs or local repro.
- Sample Sort button cycles 3 states (0 → A–Z → Z–A → 0); needs 4 FA
  rows (Name A–Z, Name Z–A, Sorted by Name A–Z, Sorted by Name Z–A).
- Sample-mode status link and search counter write English runtime text;
  observer translates only FA-keyed strings.
- STATUS_LABEL bug: old code read badge.textContent (Persian in fa) and
  never restored English. Fix: STATUS_LABEL map of English keys.
- Sample mode content display:none until .is-active; static never paints.
  Use dynamic counter templates only.

Migrations / hooks:
- PostgreSQL UnsafeNewEnumValueUsage: when a migration compares an enum
  column to a value added in the same transaction (e.g. 0014 adds
  'document_ingestion'; 0047 uses it in a WHERE, and env.py runs all
  migrations in one transaction), the migration fails on a fresh DB.
  Cast to ::text or use autocommit_block(). Local dev never catches
  this; only CI's fresh-DB run does. Pre-push fresh-DB upgrade-head
  check is now routine.
- Pre-commit hook runs pytest against the WORKING TREE, not staged
  content. Any uncommitted file (e.g. half-built model) can block an
  unrelated commit. For multi-file sub-steps, either finish the whole
  set before committing or stash the in-progress files (byte-check the
  restore).

Session / memory:
- Pause / partial-session recovery: if a step ships but memory was not
  written, the drift check reports STATE DRIFT (anchor = new hash, §3
  sha = old hash). Resolve by writing the pending memory, not by
  reverting. Verify CI on the anchor commit first; if green, memory
  reflects it; if red, do NOT write memory (the drift is a signal that
  a red commit exists).
- NOT_TRACKED overloading: means "backend doesn't track this stage at
  all" (evidence, knowledge) when detail is null, and "didn't run
  because conversion failed" (structure, ocr on FAILED/UNSUPPORTED)
  when detail says so. UI must disambiguate by detail.
- Rule 1 discipline in check messages: when approving a plan, do not
  override it in a later check message. If a check contradicts
  Section 4/D21 (e.g. "upload/security must always stay derived"),
  that contradicts the approved plan. Either amend the plan
  explicitly or accept it. This session had one such contradiction:
  D26 corrected my message, not the code.
- Merge semantics: stage-rows override derived per stage_key when the
  row exists for the latest job; upload/security rows only exist for
  initial uploads (D15), so reprocess and URL jobs naturally stay
  derived. The unique constraint on (sync_job_id, stage_key)
  guarantees one row per stage.
- Memory commit ordering: when a step's memory (vN) is written before
  CI completes, §3 records "in_progress". vN+1 updates it to green. Do
  not amend a docs commit for one line; do not create a standalone
  docs commit just for a CI status change.
- i18n infinite loops: never map an English key to an identical FA
  value (e.g., "OCR": "OCR"). The mutation observer will rewrite the
  text node endlessly. Use .identifier or skip the FA entry instead. No
  static check catches this; only browser tests do.
- i18n status label conflicts: the FA key "Open" was already mapped as
  a verb ("to open"). For gap statuses use "Still open" to avoid the
  clash. Check an existing key's meaning before reusing it for a value.

### 10.3 Reversals and abandoned approaches

- sudo mkdir /var/lib/aiol && chmod 777 → security anti-pattern. Replaced
  by AIOL_SOURCE_STORE=${{ runner.temp }}/...
- job-level env AIOL_SOURCE_STORE → GitHub rejects runner context.
  Replaced by step-level env.
- ubuntu-latest → Ubuntu 26 migration broke. Replaced by ubuntu-24.04.
- Local Docker full-suite repro for CI diagnosis → too slow, cleaned up.
- Playwright MCP browser → profile locked. Replaced by bundled scripts.
- 8-count overview in Live mode → duplicated Sources, ~10 requests.
  Replaced by 4-card summary only.
- 3 sample source detail pages collapse to 1 → only 1 exists.
- Remove Sources sample rows → Knowledge kept samples. Replaced by keep
  7 rows with 5 fixes.
- English-first 7B2b, add FA later → 2nd i18n-coverage rule catches it.
  Replaced by 7B2b ships own FA from 7B2a.
- Add source 4 cards → no backend ingestion for Dataset/Site. Replaced
  by 2 cards + debt.
- Force-push to fix BOM → shared branch, CI running. Leave BOM, fix
  during natural rebase; harden process.
- «پژوهش گیاهی» for plant → inconsistent. Replaced by «گیاه».
- Row 3 "Showing all 8 sources." static fallback → screens display:none
  until .is-active. Replaced by dynamic templates.
- Row 21 "View" as new FA key → reuse Knowledge's «حالت نمایش».
- --require repeated flags → arg() used indexOf, only first read. Replaced
  by args() + dedupe (7A4a).
- check application/pdf via <(…|identifier)\b → identifier is class, not
  tag. Replaced by class-based regex.

### 10.4 Historical context (env, setup, non-code)

- User on Windows PowerShell at C:\Users\Hamed\Downloads\1- AI-Operating-Layer;
  real nested repo is graphify-src/02-core-tool-full-repo.
- AIOL includes separate website, dashboard prototype, FastAPI Cloud Core,
  WordPress plugin.
- Larger goal: all dashboard screens backend-connected, fully bilingual
  Persian/English with RTL + Persian digits, tested, visually elevated
  using Impeccable/design-taste.
- Docker Desktop/WSL intermittent issues; low memory when API server +
  harness + Playwright/Chrome ran together; background servers reaped.
- Docker Desktop must be manually started for local Postgres tests.
  Postgres in aiol_postgres container.
- Cloud Core dev server typically uvicorn at 127.0.0.1:8010 (some 8000).
- GitHub API unauth limit 60 req/hr. User often checks UI manually.
- The AIOL repo is at C:/Users/Hamed/Downloads/1- AI-Operating-Layer/
  graphify-src/02-core-tool-full-repo. Do not run git from
  C:/Users/Hamed (the home directory contains an unrelated .git with
  personal files that must never be touched). Always `cd` into the
  repo path first, or use absolute paths.
- Alembic venv: cloud-core/.venv/Scripts/alembic.exe (Windows path).
  The repo-root .venv does not exist. To run alembic current:
  `cd cloud-core && .venv/Scripts/python -m alembic current`.

### 10.5 Open threads (outside current 7-series)

- 7B2 full detail with backend for Archive/Delete/version/tabs — needs
  backend design for source archive state + per-source tabs filter +
  version history.
- 7C Processing — done (see §4). 7D and 7E remain.
- 7D Provenance (frontend only, 3+3N calls).
- 7E Add source (Upload + URL only, ~1h).
- Step 8 (Knowledge tools) partially complete: 8A, 8C, 8D done; 8B
  remains. V5-matrix-coverage-runtime-fa is OPEN.
- Steps 9–14 (AI, Visibility, Commerce, Website+Auth, Settings, Admin)
  — not started. Admin blocked on backend design for
  platform-admin API + authorization model.
- Design elevation across all screens — baseline Knowledge critique
  started; no fixes yet.
- Full E2E of Memory Center, AI providers, Agent Network — not tested;
  no API keys; needs credentials + targeted tests.

### 10.6 ADRs, constants, and invariants

- ADR-024: no invented composite scores.
- check.js enforces 33 static UI checks, incl. "no invented composite
  score". Keep it passing.
- CI uses pgvector/pgvector:pg16 (migrations enable vector extension).
- derived_status precedence in /sources/overview:
  failed > processing > completed > abstract_only > reference_only.
  last_activity_at = GREATEST(source.updated_at, MAX(documents.updated_at)).
- Knowledge finished = published AND 0 conflicts AND 0 gaps AND 0 pending
  evidence AND status IN (approved, published); "approved" doesn't exist
  on knowledge objects, so effectively published. Implemented as
  status = published.
- source_type is free-text (not enum). Known values: plant, ingredient,
  compound, topic, product, concept, scientific_paper, book, pdf, website,
  government, dataset, first_party, review, news, lab_report, user_upload,
  supplier_document. Unknown types render raw English in <bdi>.
- Sources sample table = 7 columns (Source, Status, Knowledge, Claims,
  Evidence, Updated, Actions/Open). Live also 7 (Open 7th, header
  screen-reader-only). Hash query: #screen-sources?status=.
- e2e/seed.py seeds one org. e2e/seed-edge-cases.py seeds 5 edge states.
  Cleanup = SQL DELETE FROM organizations (no org-deletion API; cascade
  verified across 121 tables).
