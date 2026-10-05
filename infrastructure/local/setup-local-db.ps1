# One-time local database setup. Asks for your 'postgres' password once.
#
# Run (normal PowerShell, no admin needed):
#   powershell -ExecutionPolicy Bypass -File "D:\claude\attendance-system\infrastructure\local\setup-local-db.ps1"

$ErrorActionPreference = 'Stop'

$root    = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$envFile = Join-Path $root 'backend\.env'
$sqlFile = Join-Path $root 'database\setup\create_local_databases.sql'

if (-not (Test-Path $envFile)) { throw "Missing $envFile - copy backend\.env.example to backend\.env first." }

# Read KEY=VALUE lines from backend\.env
$cfg = @{}
foreach ($line in Get-Content $envFile) {
    if ($line -match '^\s*([A-Z_]+)\s*=\s*(.*)\s*$') { $cfg[$Matches[1]] = $Matches[2] }
}

$psql = (Get-Command psql -ErrorAction SilentlyContinue).Source
if (-not $psql) { $psql = 'C:\Program Files\PostgreSQL\16\data\bin\psql.exe' }
if (-not (Test-Path $psql)) { throw 'psql.exe not found. Open a NEW PowerShell window or check the PostgreSQL install.' }

Write-Host "Connecting to PostgreSQL at $($cfg.DB_HOST):$($cfg.DB_PORT) as 'postgres'..."
Write-Host "Type your 'postgres' password when asked (nothing appears while typing)." -ForegroundColor Yellow

& $psql -h $cfg.DB_HOST -p $cfg.DB_PORT -U postgres -d postgres `
    -v "owner_password=$($cfg.DB_OWNER_PASSWORD)" `
    -v "app_password=$($cfg.DB_APP_PASSWORD)" `
    -f $sqlFile

if ($LASTEXITCODE -ne 0) { throw "Setup failed (psql exit code $LASTEXITCODE). See the message above." }
Write-Host 'Local databases are ready.' -ForegroundColor Green
