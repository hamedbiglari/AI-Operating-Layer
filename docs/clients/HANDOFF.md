# Client suite — handoff (resume here)

Branch: `claude/nice-fermi-du1d71` (pushed). ADRs: 137 (clients), 138 (Device Intelligence).
Full report: `docs/clients/CLIENT_SUITE_REPORT.md`. Build guide: `clients/README.md`.

## Done (verified)
- Cloud Core: native session routes, chat `client_request_id`, `/clients/config`, `/devices/*`, migration 0049.
  Full suite on a fresh DB: 1794 passed, 0 failed, coverage 93.54 %.
- Shared UI (`clients/app`): 30/30 unit tests, 39/39 end-to-end checks against a live Cloud Core.
- Tauri shell (`clients/src-tauri`): 5/5 Rust tests; type-checks for Windows and Android.
- Commits: 7c73827 (backend + CI), 1e1bca8 (clients), f8372ea (docs), 01b4467 (sorting + test fix).

## In progress
- CI "Client suite CI" run 41209523146 on 01b4467:
  https://github.com/hamedbiglari/AI-Operating-Layer/actions/runs/41209523146
  Jobs: shared, e2e, shell-tests, Package Windows, Package macOS, Android debug APK, iOS simulator.
  Next step: read its result; fix any failing job; record outcomes in CLIENT_SUITE_REPORT.md §4–7 / §17.

## Next steps, in order
1. CI result above → fix failures → update platform statuses (BUILD VERIFIED / PACKAGE GENERATED only
   with job evidence).
2. Signing: add secrets named in clients/README.md (Authenticode, Apple Developer ID + notarization,
   Android keystore, Apple team) — owner action.
3. Repository variable `AIOL_API_BASE_URL` (https production API) — owner action.
4. Debt rows `CLIENT-*` in docs/ai-context/DEBT_REGISTER.md (dashboard Device Intelligence screen,
   retention scheduler, streaming, OIDC, updater, mobile billing, attestation, CSP narrowing).
5. Real-device tests on Windows, macOS, Android, iPhone/iPad; legal review of the privacy text.

## Local environment notes (lost when the container is reclaimed)
Postgres 16 + pgvector at /tmp/pgdata (port 5432, user aiol/aiol_dev_password), Redis 6379,
venv /tmp/venv. Fresh DB for tests: create DB, `alembic upgrade head`, then pytest.
