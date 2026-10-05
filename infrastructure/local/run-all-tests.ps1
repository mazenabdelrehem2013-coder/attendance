# Runs every automated test of the project and prints one summary at the end.
#   powershell -ExecutionPolicy Bypass -File D:\claude\attendance-system\infrastructure\local\run-all-tests.ps1
#   ... -LoadTest     also runs the morning-rush load test (500 check-ins in 2 minutes, ~3 minutes)
param([switch]$LoadTest)

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$results = [ordered]@{}

function Step($name, $folder, [scriptblock]$command) {
    Write-Host "`n=== $name ===" -ForegroundColor Cyan
    Push-Location (Join-Path $root $folder)
    try {
        & $command
        $results[$name] = if ($LASTEXITCODE -eq 0) { 'PASSED' } else { 'FAILED' }
    } finally {
        Pop-Location
    }
}

Step 'Backend (API + database)' 'backend' { .\.venv\Scripts\python -m pytest --cov=app --cov-report=term:skip-covered }
Step 'Dashboard (web)' 'dashboard' { npm.cmd test }
Step 'Mobile app' 'mobile' { flutter test }
if ($LoadTest) {
    Step 'Load test: 500 check-ins in 2 minutes' 'backend' { .\.venv\Scripts\python scripts\load_test.py --employees 500 --window 120 }
    Step 'Load test: 200 double taps' 'backend' { .\.venv\Scripts\python scripts\load_test.py --employees 200 --window 10 --double-tap }
}

Write-Host "`n=== Summary ===" -ForegroundColor Cyan
foreach ($r in $results.GetEnumerator()) {
    $colour = if ($r.Value -eq 'PASSED') { 'Green' } else { 'Red' }
    Write-Host ("{0,-45} {1}" -f $r.Key, $r.Value) -ForegroundColor $colour
}
if ($results.Values -contains 'FAILED') { exit 1 }
