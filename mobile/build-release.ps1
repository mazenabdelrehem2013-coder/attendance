# Builds the signed Google Play release (app bundle) of Raya Attendance.
#   powershell -ExecutionPolicy Bypass -File D:\claude\attendance-system\mobile\build-release.ps1
# Before each NEW upload, raise the version in pubspec.yaml, e.g.  version: 1.0.1+2
# (the number after + must always go up). Needs the upload key in D:\claude\keys
# (android\key.properties points to it).
$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot
$env:PATH = "D:\flutter\bin;$env:PATH"
$env:PUB_CACHE = 'D:\dev-cache\pub'
$env:GRADLE_USER_HOME = 'D:\dev-cache\gradle'

if (-not (Test-Path "$root\android\key.properties")) { throw 'android\key.properties is missing (the upload key). See docs\19-android-release.md.' }

$api = 'https://raya.34.35.174.159.nip.io/api/v1'
$cloudProject = '929211013841'   # Google Cloud project linked in Play Console for Play Integrity
Push-Location $root
flutter test
if ($LASTEXITCODE) { Pop-Location; throw 'Tests failed - not building a release.' }
flutter build appbundle --release --dart-define=API_BASE_URL=$api --dart-define=CLOUD_PROJECT_NUMBER=$cloudProject
$ok = $LASTEXITCODE -eq 0
Pop-Location
if (-not $ok) { throw 'Build failed. If Gradle reports a network error, simply run this script again.' }

$version = (Select-String -Path "$root\pubspec.yaml" -Pattern '^version:\s*(\S+)').Matches[0].Groups[1].Value
$target = "$root\store\out\raya-attendance-$($version.Replace('+', '-build')).aab"
New-Item -ItemType Directory -Force "$root\store\out" | Out-Null
Copy-Item "$root\build\app\outputs\bundle\release\app-release.aab" $target -Force
Write-Host "`nReady to upload to Google Play: $target" -ForegroundColor Green
