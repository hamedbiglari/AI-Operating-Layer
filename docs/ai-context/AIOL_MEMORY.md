# AIOL MEMORY — single source of truth

<!-- This file is the only memory. Any other handoff is stale.
     AUTHORITATIVE ONLY IF `sha:` below matches:
       git log --oneline -1 --grep='^docs: AIOL_MEMORY' --invert-grep | cut -c1-7
     i.e. the last NON-docs commit. Docs commits (this file's own updates)
     never move `sha:`. -->

## 0. How to use this file (read first)

You are the planning/review assistant. You do NOT see the code. The user
pastes your prompts into Claude Code and pastes Claude Code's replies back.
You have zero memory between sessions. This file IS your memory.

On load:
1. Verify the SHA: run the command in the HTML comment at top. Compare to
   `sha:` below. If they differ → say "STATE DRIFT", list what differs,
   wait for the user to reconcile. Do not proceed.
2. If in sync → summarize current state in 2–3 sentences.
3. Wait for the user's "go" before proposing anything.
4. Never say "I remember" — read from this file or what the user pastes.

End of session: user invokes end ritual. Regenerate this ENTIRE file from
scratch (do not diff). Output only the file content.

## 1. Project identity

- Repo: C:\Users\Hamed\Downloads\1- AI-Operating-Layer\graphify-src\02-core-tool-full-repo
- Branch: v5-implementation
- Stack: FastAPI backend (cloud-core/app) + single-page HTML harness
  (visual-harness/index.html, ~12,300 lines, edited directly)
- Goal: wire 52 mock screens to real backend, translate to Persian,
  lock translation coverage in CI.
- Language: Persian for explanation, English for code/commits.

## 2. Working rules (do NOT re-derive, do NOT relax)

1. CI-first: diff → user approves → commit → push → CI green → next.
   Never commit before showing the diff.
2. Bidi: build Persian strings from explicit codepoints. Verify with
   check-persian.js.
3. Two-check rule before UI commits:
   node visual-harness/check-persian.js → exit 0
   node visual-harness/i18n-coverage.js --require <screens> → 0, exit 0
4. Test rule: new tests must FAIL pre-fix and PASS post-fix. Prove by
   stashing the fix, running, restoring, running again.
5. Scope: backend commit before frontend. No schema change without asking.
   No touching billing/auth/payments without approval.
6. Debt: deferred work → docs/ai-context/DEBT_REGISTER.md
   {name, description, status: OPEN, category}. Never in code comments.
7. Small commits: one concept per commit, each shippable.
8. No force-push. Amend before push only.
9. Long diffs truncate. Ask Claude Code for ~30-line snippets.
10. This file is updated ONLY at end-of-session, as its own docs commit,
    separate from code commits.

## 3. Repository state (verifiable)

- sha (last non-docs commit): 97325af
- branch: v5-implementation
- working_tree: dirty — 7B1 code+tests uncommitted (see §5)
- last_ci: green @ 97325af
- last code commit: "7A4: Sources screen fully translated, locked in CI"

## 4. Completed steps (compact)

- Step 5 — Foundation: glossary, i18n core + Jalali, coverage scanner,
  source-char scanner. All in CI. Green.
- Step 6 — Knowledge screen: live, bilingual, 106 browser checks,
  CI-locked 100%. Backend /knowledge/overview. Green.
- Step 7A — Sources list: live, bilingual, 64 browser checks,
  CI-locked 100%. Backend /sources/overview with counts + derived_status.
  Sub-commits: 7A1, 7A2a, 7A2b, 7A3a/b/c, 7A4, 7A4a. Green @ 97325af.

## 5. In progress

Step 7B — Source detail (minimal), sub-step 7B1 only.
- Spec: add `id` query param to GET /sources/overview. When `id` present,
  ignore search/type/status/sort/limit/offset; return 0 or 1 row. 404 for
  unknown id OR cross-org id. No `id` → byte-identical to today.
- Status: code+tests written in working tree, NOT committed.
- Decisions locked (do not re-ask):
  a. id ignores all other filters. WHERE org=? AND id=?.
  b. Error shape = app's {"error":{"message":...}}, same text as existing
     source-404 helper. Not FastAPI's {"detail":...}.
  c. Add explicit "no id, list unchanged" regression-guard test
     (passes pre- and post-fix by design; say so in the test).
  d. Fail-before/pass-after mandatory. Expect cases 1–3 fail pre-fix,
     case 4 passes both. If any of 1–3 doesn't fail pre-fix, stop and
     report. Case 3 pre-fix proves missing 404-on-cross-org, NOT leak
     protection (tenant filter already protects).
  e. Backend-only; still run check-persian.js and i18n-coverage.js
     --require, report exit codes.
- Awaiting from Claude Code before commit approval:
  diff snippets (router, service, test), pre-fix FAIL output, post-fix
  PASS output, full-file pytest exit code, both Persian CI exit codes,
  proposed commit subject.
- Commit subject proposal: `7B1: id filter on GET /sources/overview + tests`

## 6. Next action

Case A — Claude Code returned diff+evidence:
  If all 7 deliverables present and pre-fix FAIL evidence is correct →
  send "commit".
  If anything missing or FAIL evidence wrong → send focused fix prompt,
  do not commit.

Case B — Commit done and CI green:
  Move to 7B2a: `docs(i18n): Source detail glossary for review` — prepare
  glossary rows for user review BEFORE any code touches the detail screen.

Case C — STATE DRIFT detected:
  Stop. Ask user to update §3 or report actual HEAD. Do not propose work
  until resolved.

## 7. Open decisions (blocking)

(none currently)

## 8. Preferences

- Persian speaker; Windows PowerShell.
- User runs Claude Code CLI separately. You are planning/review only.
- Wants explicit "decision needed" lists over assumptions.
- Commits only after explicit approval.
- No "waiting for CI" filler — report progress only.
- GitHub API rate-limited; user checks UI manually.

## 9. Changelog

- v1 — created from a fresh chat. Captures 7B1 in-progress, decisions a–e
  locked, three next-action cases. sha: 97325af.
