# Sandbox verification addendum — 2026-09-18

This folder was produced by a **different** Claude session (this one — the
claude.ai chat sandbox), on a different machine than the one that wrote
`docs/phase13/PHASE13_REPORT.md`. It does not replace that report. It adds
one more, independently-run data point, and it changes nothing else in
this package. The code in `cloud-core/`, `wordpress-plugin/`, `frontend/`
and `docs/` is exactly what was already in the uploaded
`AI-Operating-Layer-Phase13-IMPLEMENTED-NOT-VERIFIED` package — untouched.

## Environment, confirmed again, independently

```
$ python3 -c "import fastapi"     -> ModuleNotFoundError
$ python3 -c "import sqlalchemy"  -> ModuleNotFoundError
$ python3 -c "import pytest"      -> ModuleNotFoundError
$ python3 -c "import alembic"     -> ModuleNotFoundError
$ pip3 install pytest             -> "No matching distribution found" (no network egress)
$ which php                       -> not found
$ curl https://pypi.org           -> HTTP 403 from the network proxy
```

This is the same class of blocker the original report describes, in a
separate sandbox. It is a property of the execution environment, not a
choice made by this session, and it was not worked around by installing
anything, faking a database, or claiming an untested path is tested.

## What this session actually ran (all logs in this folder)

| Check | Command | Result | Log |
|---|---|---|---|
| Python syntax, whole tree | `python3 -m py_compile` on every `.py` file | **273/273 compiled, 0 errors** | `py_compile_all.log` |
| JS visual-harness build | `node visual-harness/build.js` | wrote `index.html`, 74 icons | (stdout above) |
| JS static UX conformance | `node visual-harness/check.js` | **33/33 passed, 0 failed** | `visual_harness_check.log` |
| JS visual gate | `node visual-harness/measure.js` | correctly reports **ENVIRONMENT BLOCKED** (no Chromium) — it does *not* report a false pass | `visual_harness_measure.log` |
| Standalone production-logic tests | `python3 sandbox_logic_tests.py` | **12/12 passed** | `sandbox_logic_tests.log` |

### What `sandbox_logic_tests.py` actually does

It imports the real, unmodified `cloud-core/app/services/actor_signatures.py`
and `cloud-core/app/models/enums.py` — the only two Phase 13 files with no
FastAPI/SQLAlchemy dependency — by registering empty stand-in packages for
`app`, `app.models`, `app.services` in `sys.modules` so Python's package
loader doesn't try to import the framework-dependent siblings. It does not
alter, stub, or reimplement any logic inside those two files.

It then calls the real `match()` function against realistic User-Agent
strings and asserts on the real return values:

- `GPTBot`, `ClaudeBot`, `Googlebot`, `ChatGPT-User`, `Claude-User` each
  classify to the actor type / purpose the module claims.
- The order-sensitive case the module's own docstring warns about —
  `Claude-SearchBot` must not be swallowed by the later, broader
  `ClaudeBot` needle — is checked explicitly, against the real ordering
  in `SIGNATURES`, and passes.
- An ordinary Chrome UA and an unrecognised crawler both correctly return
  `None` (no guessing).
- Empty/whitespace UA returns `None` without raising.

It also does one static cross-check that was listed as an **open forensic
concern** in `PHASE13_REPORT.md` §7 item 2 (only the signature *lists* were
said to be parity-tested, not exercised together): it regex-extracts the
36-entry `$signatures` array from
`wordpress-plugin/includes/class-aiol-actors.php` and asserts its keys
match `actor_signatures.needles()` **in the same order**. They do. This is
a text-level comparison of the two files as committed — it does not
execute the PHP file, because no PHP interpreter is available here either.

## What this does **not** prove, and why nothing further was attempted

`access_policy_service.py`, `telemetry_service.py`, `ai_agent_service.py`
and `search_demand_service.py` import SQLAlchemy's `select`/`Session` and
FastAPI's `HTTPException` at module level and use the ORM's query-building
directly (`AccessPolicy.agent_id.is_(...)`, `.scalar_one_or_none()`,
composite tenant filters, etc.). Faking those imports well enough to
import the modules is possible; faking them well enough that a pass
*means* the ORM behaviour is correct is not — a shallow mock would
exercise the branching in `evaluate()` while saying nothing about the
real query it builds, the composite foreign key it depends on, or how
Postgres's `UNIQUE NULLS NOT DISTINCT` behaves. Shipping that as "tested"
would be exactly the failure mode `PHASE13_REPORT.md` §0 and the MASTER
document's own rules name directly: *treating fixtures as live provider
verification, treating blocked environments as PASS*. So it wasn't done.
The honest status for those four services, the router, the migration, and
all ~50 written pytest cases remains what §6.2 of `PHASE13_REPORT.md`
already says: **written, not executed**, until run against real
Postgres/Redis with `pip install -r requirements.txt` and
`python -m pytest`.

## Net effect on the verdict

`FINAL PHASE 13 STATUS: BLOCKED` (as set in `PHASE13_REPORT.md`) is
**unchanged**. What changed is the evidence base: two additional
independent runs confirm the syntax/static claims, and one small but real
functional test (not merely "it parses") now backs the actor-classification
logic and its PHP/Python parity — the one piece of Phase 13 that had no
framework dependency and so was actually possible to execute here.
