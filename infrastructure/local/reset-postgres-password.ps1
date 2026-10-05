#Requires -RunAsAdministrator
# Resets the password of the local PostgreSQL 'postgres' superuser.
#
# How it works:
#   1. Backs up pg_hba.conf (the file that controls who may log in).
#   2. Temporarily allows ONLY user 'postgres' from this PC (127.0.0.1) without a password.
#   3. Asks you to type a new password (twice). It is never shown or saved in a file.
#   4. ALWAYS restores the original pg_hba.conf and restarts PostgreSQL, even if something fails.
#
# Run from an Administrator PowerShell:
#   powershell -ExecutionPolicy Bypass -File "D:\claude\attendance-system\infrastructure\local\reset-postgres-password.ps1"

$ErrorActionPreference = 'Stop'

$dataDir = 'C:\Program Files\PostgreSQL\16\data\data'   # (this install is PostgreSQL 18 despite the folder name)
$binDir  = 'C:\Program Files\PostgreSQL\16\data\bin'
$service = 'postgresql-x64-18'

$hba    = Join-Path $dataDir 'pg_hba.conf'
$backup = "$hba.backup-before-reset"

if (-not (Test-Path $hba)) { throw "pg_hba.conf not found at $hba" }

Copy-Item $hba $backup -Force
Write-Host "Backed up pg_hba.conf to $backup"

try {
    @(
        '# TEMPORARY - password reset in progress. The original file is restored automatically.'
        'host    all    postgres    127.0.0.1/32    trust'
    ) | Set-Content -Path $hba -Encoding ascii

    Write-Host 'Restarting PostgreSQL with temporary settings...'
    Restart-Service -Name $service

    Write-Host ''
    Write-Host "Type a NEW password for the 'postgres' user, then type it again to confirm." -ForegroundColor Yellow
    Write-Host 'Nothing appears on screen while you type - that is normal.' -ForegroundColor Yellow
    & (Join-Path $binDir 'psql.exe') -h 127.0.0.1 -U postgres -d postgres -c '\password postgres'
    if ($LASTEXITCODE -ne 0) { throw 'Changing the password failed (see the message above).' }

    Write-Host 'Password changed.' -ForegroundColor Green
}
finally {
    Copy-Item $backup $hba -Force
    Restart-Service -Name $service
    Write-Host 'Original security settings restored and PostgreSQL restarted.' -ForegroundColor Green
}
