# Build a release on this PC and install it on the server (with automatic roll-back).
#   powershell -ExecutionPolicy Bypass -File D:\claude\attendance-system\infrastructure\server\deploy-from-pc.ps1
#   ... -Install    first time only: also runs install.sh (packages, database, nginx, HTTPS)
param([switch]$Install)
# Native tools (gcloud, npm, tar) print progress on stderr; Windows PowerShell 5.1 would treat that
# as an error, so failures are detected through their exit codes instead.
$ErrorActionPreference = 'Continue'
$PSDefaultParameterValues['*:ErrorAction'] = 'Stop'   # but PowerShell's own commands (Copy-Item...) stop on error

$Domain  = 'raya.34.35.174.159.nip.io'
$Vm      = 'tracking'
$Zone    = 'africa-south1-b'
$Project = 'gen-lang-client-0101078644'
$gcloud  = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
$root    = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$stage   = Join-Path $env:TEMP 'attendance-release'

Write-Host '== 1. Building the dashboard' -ForegroundColor Cyan
Push-Location (Join-Path $root 'dashboard'); npm.cmd run build; if ($LASTEXITCODE) { throw 'Dashboard build failed' }; Pop-Location

Write-Host '== 2. Packing the release (code only: no secrets, tests or local data)' -ForegroundColor Cyan
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force "$stage\backend", "$stage\static", "$stage\server" | Out-Null
Copy-Item -Recurse (Join-Path $root 'backend\app'), (Join-Path $root 'backend\alembic') "$stage\backend"
Copy-Item (Join-Path $root 'backend\alembic.ini'), (Join-Path $root 'backend\requirements.txt'), (Join-Path $root 'backend\constraints.txt') "$stage\backend"
Copy-Item -Recurse (Join-Path $root 'dashboard\dist\*') "$stage\static"
Copy-Item (Join-Path $root 'infrastructure\server\*'), (Join-Path $root 'database\setup\create_production_database.sql') "$stage\server"
Get-ChildItem -Recurse -Directory -Filter __pycache__ $stage | Remove-Item -Recurse -Force
$bundle = Join-Path $env:TEMP 'attendance-release.tar.gz'
tar.exe -czf $bundle -C $stage backend static server
if ($LASTEXITCODE) { throw 'Packing failed' }

Write-Host '== 3. Uploading to the server' -ForegroundColor Cyan
& $gcloud compute scp $bundle (Join-Path $root 'infrastructure\server\start-on-server.sh') "${Vm}:." --zone $Zone --project $Project
if ($LASTEXITCODE) { throw 'Upload failed' }

Write-Host '== 4. Installing on the server' -ForegroundColor Cyan
# Long SSH sessions to this server can drop: the work runs in the background on the server and
# this PC follows its log with short, simple commands.
$mode = if ($Install) { "install $Domain" } else { 'deploy' }
& $gcloud compute ssh $Vm --zone $Zone --project $Project --command "bash start-on-server.sh $mode"
if ($LASTEXITCODE) { throw 'Could not start the installation on the server' }

$shown = 0
while ($true) {
    Start-Sleep -Seconds 10
    $log = @(& $gcloud compute ssh $Vm --zone $Zone --project $Project --command 'cat attendance-setup/log' 2>$null)
    if ($log.Count -gt $shown) {
        $log[$shown..($log.Count - 1)] | Where-Object { $_ -notmatch '^DEPLOY_EXIT=' } | ForEach-Object { Write-Host $_ }
        $shown = $log.Count
    }
    $exit = $log | Where-Object { $_ -match '^DEPLOY_EXIT=\d+' } | Select-Object -First 1
    if ($exit) {
        if ($exit -ne 'DEPLOY_EXIT=0') { throw 'Installation on the server failed (see the messages above)' }
        break
    }
}

Write-Host "`nDone: https://$Domain" -ForegroundColor Green
