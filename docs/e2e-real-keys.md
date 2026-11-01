# Real-key end-to-end test

`visual-harness/e2e/real-keys.js` drives the harness against a **live** AI Core that makes **real** provider
calls. It is not in CI and nothing runs it automatically: every run spends money on the provider account
whose key you give it. Run it by hand when you want proof that the whole chain works with a real model.

What it checks, in order:

1. **AI Center** (`#screen-ai-center`): adds a provider (adapter `anthropic`), an account and that account's
   credential **through the forms**, then presses **Test connection** and expects `PASS`.
2. **Model and routing policy** (API): registers the model on that provider and a `manual_single` routing
   policy with one step on the new account, so a command has somewhere to run.
3. **Chat** (`#screen-chat`, the Command workspace): New, a synthesis request on your topic with that policy,
   **Plan**, **Run**, then waits until the worker finishes it (`completed` or `completed_with_gaps`).
4. **AI executions** (`#screen-ai-executions`): connects and finds the call: this model, status `succeeded`,
   started during this run.

At the end it **revokes the test credential** (`DELETE /ai-center/accounts/{id}/credential`), so the real key
does not stay stored in the database. The provider, account, model and policy rows stay (labelled
`e2e-real-<timestamp>`); delete them in AI Center when you no longer want them.

## Quick start (Windows, one command)

`scripts/start-real-e2e.ps1` does steps 1 and 3 below for you: it checks the variables, starts postgres,
redis and the Celery worker with docker compose (migrations run first), starts AI Core locally on port 8010,
runs `real-keys.js`, and stops the backend afterwards, also when a check fails.

```powershell
$env:ANTHROPIC_API_KEY = 'sk-ant-...'      # your key
$env:AI_CREDENTIAL_KEY = '<Fernet key>'    # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
$env:AIOL_TOKEN        = '<owner/admin access token>'          # see step 2
$env:AIOL_TOPIC_ID     = '<knowledge object id with evidence>' # see step 2
.\scripts\start-real-e2e.ps1               # add -StopStack to stop the containers at the end
```

Before the first run: `cloud-core\.venv` must exist with `pip install -r requirements.txt` done (the pinned
FastAPI matters), Docker must be running, and `PLAYWRIGHT_CORE` should point at a playwright-core install
(the script looks in the global npm folder if it is not set; `PW_EXE` is optional). The worker container runs
in development mode with your `AI_CREDENTIAL_KEY`, so it can decrypt the credential the backend stores; keep
the same key between runs. The token and the topic must come from the database the stack uses (step 2, with
the backend on port 8010). If your `.env` changes `POSTGRES_*` or the ports, set the same values in the
shell before running the script.

The manual steps below do the same by hand, on any OS.

## Which key does what

| Variable | Read by | Needed here |
|---|---|---|
| `ANTHROPIC_API_KEY` | this script: typed into the AI Center credential form. AI Core also reads it from its own environment for the environment-level Anthropic adapter (Phase 17). | **Yes** (the script's environment) |
| `OPENAI_API_KEY` | AI Core's environment-level OpenAI adapter only. AI Center accounts have no OpenAI adapter yet (`IMPLEMENTED_ADAPTERS` is Anthropic only), so this suite cannot test an OpenAI account. | Optional (AI Core's environment) |
| `AI_CREDENTIAL_KEY` | AI Core: encrypts account credentials at rest (a Fernet key). Without it a credential cannot be stored. | **Yes** (AI Core's environment) |
| `AI_MODEL_PRICING_JSON` | AI Core: turns tokens into an estimated cost. Without it the cost is recorded as unknown (never as zero). | Optional |

Keys are read from the environment only. Never put them in a file inside the repository, a command you
commit, or a shell history you share.

## 1. Start AI Core with real keys

Postgres, Redis and the Celery worker must be up: a workspace **Run** is executed by the worker, not by the
request.

```bash
# Postgres + Redis (and the worker, if you use the compose file for it)
docker compose up -d postgres redis

cd cloud-core
export DATABASE_URL=postgresql+psycopg://aiol:aiol_dev_password@localhost:5432/aiol
export REDIS_URL=redis://localhost:6379/0
export AI_CREDENTIAL_KEY="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
export ANTHROPIC_API_KEY=sk-ant-...          # your key
export OPENAI_API_KEY=sk-...                 # optional, see the table above
export CORS_ALLOWED_ORIGINS=http://127.0.0.1:5175   # the origin the script serves the harness on
export APP_ENV=development

pip install -r requirements.txt   # the pinned versions; an older FastAPI breaks the chat stream session
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 &
celery -A app.workers.celery_app worker --loglevel=info &
curl -s http://127.0.0.1:8000/api/v1/health/live
```

Keep the same `AI_CREDENTIAL_KEY` for as long as you keep the credentials it encrypted; with a new key the
stored ones can no longer be decrypted.

## 2. Get a token and a topic

The token must belong to an **owner or admin** (AI Center writes need it):

```bash
export AIOL_TOKEN="$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -d 'username=you@example.com' -d 'password=...' | python -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')"
```

The topic is a knowledge object in that organization **with reviewed evidence**; synthesis reads that evidence,
and with none there is nothing to send to the model:

```bash
curl -s -H "Authorization: Bearer $AIOL_TOKEN" 'http://127.0.0.1:8000/api/v1/knowledge?limit=20'
export AIOL_TOPIC_ID=<an id from the list>
```

## 3. Run it

```bash
export PLAYWRIGHT_CORE=/path/to/node_modules/playwright-core   # as for the other harness suites
export PW_EXE=/path/to/chromium                                # optional
export AIOL_MODEL=claude-haiku-5-5                             # optional; the cheapest model is the default
node visual-harness/e2e/real-keys.js
```

| Variable | Default | Meaning |
|---|---|---|
| `AIOL_BASE` | `http://127.0.0.1:8000` | AI Core origin (without `/api/v1`) |
| `AIOL_MODEL` | `claude-haiku-5-5` | provider model id for the account step |
| `AIOL_RUN_TIMEOUT_S` | `600` | how long to wait for the command to finish |
| `HARNESS_PORT` | `5175` | port the script serves `visual-harness/` on (must match `CORS_ALLOWED_ORIGINS`) |

Exit codes: `0` all checks passed, `1` a check failed (each failure is printed with what was seen), `2` the run
could not start or crashed (a missing variable, AI Core unreachable). The key is never printed: anything
the script prints has it replaced by `[key]`.

## Reading a failure

- **Test connection is not PASS**: the message after the label is the provider's answer, e.g.
  `BLOCKED_EXTERNAL_DEPENDENCY` (no `AI_CREDENTIAL_KEY`, or the key cannot decrypt), `FAIL (HTTP 401)` (a wrong key).
- **The command ends `blocked` or `failed`**: open it in `#screen-chat`; the result names the reason
  (no routing policy, budget, no readable evidence). Check the worker log as well.
- **No execution listed**: the run did not reach the model (see above), or the worker is not running.
