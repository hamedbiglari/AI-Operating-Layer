# Client suite — handoff (resume here)

Branch: `claude/nice-fermi-du1d71` (pushed). ADRs: 137 (clients), 138 (Device Intelligence).
Full report: `docs/clients/CLIENT_SUITE_REPORT.md`. Build guide: `apps/shared/README.md`.

## Done (verified)
- Cloud Core: native session routes, chat `client_request_id`, `/clients/config`, `/devices/*`, migration 0049.
  Full suite on a fresh DB: 1794 passed, 0 failed, coverage 93.54 %.
- Shared UI (`clients/app`): 30/30 unit tests, 39/39 end-to-end checks against a live Cloud Core.
- Tauri shell (`apps/shared/src-tauri`): 5/5 Rust tests; type-checks for Windows and Android.
- Commits: 7c73827 (backend + CI), 1e1bca8 (clients), f8372ea (docs), 01b4467 (sorting + test fix).

## CI results so far
- Run 41209523146: shared UI, e2e, Rust tests passed; **Windows package built** (artifact `aiol-Windows`,
  unsigned); Android failed in setup-android; macOS/iOS cancelled (macos-14 label). Both fixed in the
  workflow — check the next run.

- Run 41221954216: Windows built again; **iOS simulator build succeeded**; macOS compiled but bundling failed
  on empty signing secrets; Android failed on NDK_HOME. Both fixed in the workflow (next run).
- Branch merged with v5-implementation (77d9485), verified: 1800 backend tests pass.
- Platform signals (§16): Windows MachineGuid (HMAC on arrival, migration 0050), GDID unsupported,
  LIKELY_SHARED_CLIENT_ENVIRONMENT. Full suite 1809 passed, coverage 93.54 %.
- §19 dashboard Device Intelligence screen: DONE after merging v5-implementation (9B–9D); in CI gates.

- **Run 41223589699 (33be46e): every job green — Windows, macOS, Android (debug APK) and iOS simulator all
  built.** Artifacts: aiol-Windows, aiol-macOS, aiol-android-debug, aiol-ios-simulator (kept 14 days).

- 2026-11-01: streaming (SSE progress + validated answer), sign-in consent checkbox (ADR-139, migration 0051),
  signed desktop updater (ADR-140), theme/language buttons, conversational composer, and the standalone folders
  apps/windows, apps/macos, apps/android, apps/ios generated from apps/shared.

- Visual pass: assistant surface palette, sidebar/profile/composer pattern, "+" upload (roles), dictation, feedback.
  End-to-end 53/53 live; client unit 41/41; Rust 9/9; plugin PHP checks pass.

## In progress
- Nothing running. Latest client CI: run 41226260763 (ea47b51) green, including the Windows build of the
  MachineGuid reader. Retention purge scheduled; release CSP narrowing in place.

## Next steps, in order
1. CI result above → fix failures → update platform statuses (BUILD VERIFIED / PACKAGE GENERATED only
   with job evidence).
2. Signing: add secrets named in apps/shared/README.md (Authenticode, Apple Developer ID + notarization,
   Android keystore, Apple team) — owner action.
3. Repository variable `AIOL_API_BASE_URL` (https production API) — owner action.
4. Debt rows `CLIENT-*` in docs/ai-context/DEBT_REGISTER.md (dashboard Device Intelligence screen,
   retention scheduler, streaming, OIDC, updater, mobile billing, attestation, CSP narrowing).
5. Real-device tests on Windows, macOS, Android, iPhone/iPad; legal review of the privacy text.

## Local environment notes (lost when the container is reclaimed)
Postgres 16 + pgvector at /tmp/pgdata (port 5432, user aiol/aiol_dev_password), Redis 6379,
venv /tmp/venv. Fresh DB for tests: create DB, `alembic upgrade head`, then pytest.
