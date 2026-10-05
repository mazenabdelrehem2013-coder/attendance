# Phase 9 — Flutter Android App (foundation)

## What's installed (done for you)

| Tool | Where |
|---|---|
| Flutter 3.47 (stable) + Dart 3.13 | `D:\flutter` (added to your PATH) |
| Android SDK (already on your PC) | `D:\claude\android-sdk` (`ANDROID_HOME`) |
| Java 17 (already on your PC) | `JAVA_HOME` |
| Package + build caches | `D:\dev-cache\pub`, `D:\dev-cache\gradle` (keeps drive C: free) |
| Emulator | `cargotrace_test` (Android 15) — already on your PC |

Android Studio is **not** needed. Open the project in VS Code; installing the **Flutter** extension in VS Code is recommended (Extensions → search "Flutter" → Install).

## What the app does (Phase 9)

| Screen | |
|---|---|
| **Login** | Employee ID **or** email + password; clear errors ("Invalid login details", "Can't reach the server"); show/hide password |
| **Change password** | Forced on first login with a temporary password (nothing else is possible until changed); also in the menu |
| **Home** | Name, employee ID, department, manager, assigned location(s); live date & time; **today's status** in colour (Not checked in / Checked in / Late / Checked out / Pending review / Holiday / On leave / Day off); working hours; first check-in and hours worked; **today's attempts** with the message for each, and a red card explaining a rejected attempt; CHECK IN / CHECK OUT button (switched on in Phase 10) |
| **History** | Month by month: each day's status, first/last time, hours and location, plus a monthly summary |
| Menu | Change password, Log out |

Behind the scenes:

- **Stays logged in** using the refresh token kept in Android's encrypted storage; the 15-minute access token is renewed automatically (only one renewal at a time — the server treats a reused token as theft).
- **Session expired** (or revoked by HR) → back to the login screen with an explanation.
- **No internet** → clear message and *Try again*; being offline never logs you out.
- No secrets in the app — only the API address. App data is excluded from phone backups. Plain `http` is allowed **only in debug builds** (to reach the API on your PC).

## Run it

You need two PowerShell windows.

**Window 1 — the API** (as before):

```powershell
cd D:\claude\attendance-system\backend
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

**Window 2 — emulator + app**:

```powershell
flutter emulators --launch cargotrace_test
cd D:\claude\attendance-system\mobile
flutter run
```

The first `flutter run` takes several minutes (it downloads Android build tools once). When the app opens, log in with **`EMP-0101`** and the `SEED_DEFAULT_PASSWORD` from `backend\.env`.

While `flutter run` is active: press **r** to reload after code changes, **q** to quit.

**On your own Android phone instead of the emulator:** enable *Developer options → USB debugging*, connect by USB, accept the prompt on the phone, then (the phone can't use `10.0.2.2`; use your PC's Wi-Fi IP, e.g. `192.168.1.20`, and start the API with `--host 0.0.0.0`):

```powershell
flutter run --dart-define=API_BASE_URL=http://192.168.1.20:8000/api/v1
```

## Tests

```powershell
cd D:\claude\attendance-system\mobile
flutter test
```

Expected: `All tests passed!` (17 tests: login, wrong password, no network, empty form, home content, checked-in state, rejected-attempt explanation, session restore, session expired, offline start, forced password change, logout, token renewal and its single-renewal rule).

## Troubleshooting

| Problem | Fix |
|---|---|
| `flutter` is not recognized | Close and reopen PowerShell (PATH was updated). |
| `No devices found` | Start the emulator first (`flutter emulators --launch cargotrace_test`) and wait until the Android home screen shows. |
| App says "Can't reach the server" | The API (window 1) isn't running, or on a real phone the IP/`--host 0.0.0.0` is missing. |
| Very slow first build | Normal once (Gradle download, ~1–2 GB into `D:\dev-cache\gradle`). |
| Emulator very slow / black | Close it and start again; make sure no other emulator is running. |
