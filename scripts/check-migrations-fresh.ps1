<#
.SYNOPSIS
  Fresh-database migration check before a push (V5-migration-fresh-db-local-check).

.DESCRIPTION
  Creates a new, empty database in the local Postgres container, runs the migrations against it, and drops it.
  Your dev database is never touched.
    1. alembic upgrade head    - every migration from nothing, as CI does. This is what catches a migration that
                                 only works on an already-migrated database, such as one that uses an enum value
                                 added in the same transaction (PostgreSQL UnsafeNewEnumValueUsage).
    2. alembic downgrade -1    - the newest migration's downgrade.
    3. alembic upgrade head    - and its upgrade again.
  With -Full, step 2 is `downgrade base` instead (every downgrade), and the script checks that no application table
  is left before upgrading again (what cloud-core/scripts/verify_migration_cycle.sh does, on a disposable database).
  Exit codes: 0 clean, 1 a migration step failed (its output is shown), 2 setup failed.

.EXAMPLE
  .\scripts\check-migrations-fresh.ps1
  .\scripts\check-migrations-fresh.ps1 -Full
#>
param(
  [string]$Container = 'aiol_postgres',
  [switch]$Full
)

# Continue, not Stop: alembic logs to stderr, and Windows PowerShell 5.1 turns redirected native stderr into errors.
# Every step is checked through $LASTEXITCODE instead.
$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent $PSScriptRoot
$core = Join-Path $repo 'cloud-core'
$python = Join-Path $core '.venv\Scripts\python.exe'
$user = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { 'aiol' }
$password = if ($env:POSTGRES_PASSWORD) { $env:POSTGRES_PASSWORD } else { 'aiol_dev_password' }
$port = if ($env:POSTGRES_PORT) { $env:POSTGRES_PORT } else { '5432' }
$db = 'migcheck_' + [guid]::NewGuid().ToString('N').Substring(0, 10)

function Fail([string]$message, [int]$code) { Write-Host "ERROR: $message" -ForegroundColor Red; exit $code }
if (-not (Test-Path $python)) { Fail "No virtual environment at $python." 2 }
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail 'docker is not on PATH.' 2 }
& docker exec $Container createdb -U $user $db
if ($LASTEXITCODE -ne 0) { Fail "Could not create $db in container $Container (is it running?)." 2 }

$saved = $env:DATABASE_URL
$env:DATABASE_URL = "postgresql+psycopg://${user}:${password}@localhost:${port}/$db"
$code = 0
Push-Location $core
try {
  $steps = @(@('upgrade', 'head'), $(if ($Full) { @('downgrade', 'base') } else { @('downgrade', '-1') }), @('upgrade', 'head'))
  $n = 0
  foreach ($s in $steps) {
    $n++
    Write-Host "[$n/3] alembic $($s -join ' ')"
    $out = & $python -m alembic @s 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { Write-Host $out; Write-Host "FAILED at: alembic $($s -join ' ')" -ForegroundColor Red; $code = 1; break }
    if ($Full -and $s[0] -eq 'downgrade') {
      $left = & docker exec $Container psql -U $user -d $db -tAc "SELECT string_agg(tablename, ', ') FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
      if ($left -and $left.Trim()) { Write-Host "FAILED: tables left after downgrade base: $left" -ForegroundColor Red; $code = 1; break }
    }
  }
  if ($code -eq 0) { Write-Host "Migrations clean on a fresh database: $(& $python -m alembic current 2>$null | Select-Object -Last 1)" -ForegroundColor Green }
} finally {
  Pop-Location
  $env:DATABASE_URL = $saved
  & docker exec $Container dropdb -U $user --force $db | Out-Null
}
exit $code
