<#
.SYNOPSIS
  One-click real-key end-to-end test: AI Core + worker with real keys, then visual-harness/e2e/real-keys.js.

.DESCRIPTION
  1. Checks the required variables (ANTHROPIC_API_KEY, AI_CREDENTIAL_KEY, AIOL_TOKEN, AIOL_TOPIC_ID).
  2. Starts postgres, redis and celery-worker with docker compose (the one-shot migrate service runs
     `alembic upgrade head` first). The worker runs with APP_ENV=development and your AI_CREDENTIAL_KEY,
     so it can decrypt the test credential the backend stores.
  3. Starts AI Core locally (cloud-core\.venv) on port 8010 and waits for /api/v1/health/live.
  4. Runs node visual-harness/e2e/real-keys.js against it.
  5. Stops the backend (always, also on failure). The containers keep running; -StopStack stops them too.
  Spends real provider credit. Keys are read from the environment and never printed or written to a file.
  Full guide: docs/e2e-real-keys.md

.EXAMPLE
  $env:ANTHROPIC_API_KEY = 'sk-ant-...'
  $env:AI_CREDENTIAL_KEY = '<Fernet key>'
  $env:AIOL_TOKEN = '<owner/admin access token>'
  $env:AIOL_TOPIC_ID = '<knowledge object id with reviewed evidence>'
  .\scripts\start-real-e2e.ps1
#>
param(
  [int]$Port = 8010,
  [int]$HarnessPort = 5175,
  [switch]$StopStack
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$core = Join-Path $repo 'cloud-core'
$python = Join-Path $core '.venv\Scripts\python.exe'

function Fail([string]$message) { Write-Host "ERROR: $message" -ForegroundColor Red; exit 2 }

# 1. Required variables
$missing = @('ANTHROPIC_API_KEY', 'AI_CREDENTIAL_KEY', 'AIOL_TOKEN', 'AIOL_TOPIC_ID') |
  Where-Object { -not [Environment]::GetEnvironmentVariable($_) }
if ($missing) { Fail ("Not set: " + ($missing -join ', ') + ". See docs/e2e-real-keys.md.") }
if (-not (Test-Path $python)) { Fail "No virtual environment at $python. Create it and run: pip install -r cloud-core\requirements.txt" }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail 'docker is not on PATH.' }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Fail 'node is not on PATH.' }
if (-not $env:PLAYWRIGHT_CORE) {
  $globalRoot = (& npm root -g).Trim()
  foreach ($candidate in @("$globalRoot\playwright-core", "$globalRoot\playwright\node_modules\playwright-core", "$globalRoot\@playwright\cli\node_modules\playwright-core")) {
    if (Test-Path $candidate) { $env:PLAYWRIGHT_CORE = $candidate; break }
  }
  if (-not $env:PLAYWRIGHT_CORE) { Fail 'Set PLAYWRIGHT_CORE to a playwright-core install (npm install -g playwright-core).' }
}

# 2. Docker stack: postgres, redis, celery-worker (migrate runs first)
$env:APP_ENV = 'development'   # read by docker-compose.yml for the containers, and by the local backend below
Write-Host 'Starting postgres, redis and celery-worker (docker compose)...'
Push-Location $repo
try {
  & docker compose up -d --build postgres redis celery-worker
  if ($LASTEXITCODE -ne 0) { Fail 'docker compose up failed.' }
} finally { Pop-Location }

# 3. Local backend on $Port
$env:DATABASE_URL = 'postgresql+psycopg://{0}:{1}@localhost:{2}/{3}' -f `
  $(if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { 'aiol' }), `
  $(if ($env:POSTGRES_PASSWORD) { $env:POSTGRES_PASSWORD } else { 'aiol_dev_password' }), `
  $(if ($env:POSTGRES_PORT) { $env:POSTGRES_PORT } else { '5432' }), `
  $(if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { 'aiol' })
$env:REDIS_URL = 'redis://localhost:{0}/0' -f $(if ($env:REDIS_PORT) { $env:REDIS_PORT } else { '6379' })
$env:CORS_ALLOWED_ORIGINS = "http://127.0.0.1:$HarnessPort"
$env:AIOL_SOURCE_STORE = Join-Path $env:TEMP 'aiol-real-e2e-sources'
$log = Join-Path $env:TEMP 'aiol-real-e2e-backend.log'
Write-Host "Starting AI Core on http://127.0.0.1:$Port (log: $log)..."
$backend = Start-Process -FilePath $python -WorkingDirectory $core -PassThru -WindowStyle Hidden `
  -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$Port") `
  -RedirectStandardOutput $log -RedirectStandardError "$log.err"

$exitCode = 2
try {
  $ready = $false
  for ($i = 0; $i -lt 60; $i++) {
    if ($backend.HasExited) { break }
    try {
      $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://127.0.0.1:$Port/api/v1/health/live"
      if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { Start-Sleep -Seconds 1 }
  }
  if (-not $ready) { Fail "AI Core did not become healthy. See $log and $log.err" }

  # 4. The test
  $env:AIOL_BASE = "http://127.0.0.1:$Port"
  $env:HARNESS_PORT = "$HarnessPort"
  Write-Host 'Running visual-harness/e2e/real-keys.js...'
  & node (Join-Path $repo 'visual-harness\e2e\real-keys.js')
  $exitCode = $LASTEXITCODE
} finally {
  # 5. Stop the backend (and its child processes), always
  if ($backend -and -not $backend.HasExited) {
    & taskkill /PID $backend.Id /T /F | Out-Null
    Write-Host 'AI Core stopped.'
  }
  if ($StopStack) {
    Push-Location $repo
    try { & docker compose stop celery-worker redis postgres } finally { Pop-Location }
  }
}

if ($exitCode -eq 0) { Write-Host 'Real-key E2E: ALL PASSED' -ForegroundColor Green }
else { Write-Host "Real-key E2E finished with exit code $exitCode (1 = a check failed, 2 = the run failed)." -ForegroundColor Yellow }
exit $exitCode
