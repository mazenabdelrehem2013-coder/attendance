# Phase 17 — Testing hardening

## One command for everything

```powershell
powershell -ExecutionPolicy Bypass -File D:\claude\attendance-system\infrastructure\local\run-all-tests.ps1
```
Runs the backend, dashboard and app tests (about 6 minutes) and ends with a summary:

```
Backend (API + database)                      PASSED
Dashboard (web)                               PASSED
Mobile app                                    PASSED
```
Add `-LoadTest` to also run the load tests (about 3 more minutes).

## What is tested now

| Part | Tests | Code covered by tests |
|---|---|---|
| Backend (API, database rules, jobs) | **370** | **95%** (was 94%) |
| Dashboard | **42** | **70%** (was 55%) |
| Android app | **50** | **69%**; the rest is phone hardware code (GPS, camera, secure key storage), checked on the emulator in Phases 10 and 15 |

New in this phase:
- **A full working day, end to end** (`backend/tests/api/test_e2e_full_day.py`):
  1. HR adds an employee.
  2. The employee changes the temporary password and registers a phone; HR approves it.
  3. One employee checks in late. Another uses a fake-GPS app; HR reviews and accepts that check-in.
  4. The night job closes the day: an absence and a missing check-out are recorded.
  5. The manager's report and the Excel file show exactly that.
  6. The alerts arrive, and the audit log is complete and passes the tamper check.
- **Branches nobody had tested yet**, found with the coverage report:
  - login keys: key rotation, expired / wrong-audience / unsigned tokens, too-short secret
  - wrong current password
  - logout really ends the session
  - rejecting and switching off phones
  - re-using a request ID
  - duplicate e-mail
  - Google Play Integrity answers (OK / invalid / Google down)
  - a scheduled report that crashes (recorded once, not retried every minute)
- **Dashboard:** Employees, Locations & departments, Holidays, QR screens, Phones and Change password pages.
- **App:** the forced password change at first login and "My attendance".

## Load test: the 08:00 rush

`backend/scripts/load_test.py` creates a separate "Load Test" company in the **test** database (never your real
data). Each simulated phone has its own security key and does exactly what the app does: one-time code → signed
check-in → screen refresh. Results on this PC (2 API processes, PostgreSQL on the same machine):

| Scenario | Check-ins | Errors | Check-in time: typical / 95% / slowest |
|---|---|---|---|
| 500 employees arriving within **2 minutes** | 500 accepted | 0 | 39 ms / 53 ms / 78 ms |
| 500 employees within **15 seconds** (≈ 96 requests per second, 100 phones at the same moment) | 500 accepted | 0 | 405 ms / 631 ms / 990 ms |
| **Double tap**: 200 phones each send 2 check-ins at the same instant | exactly 200 accepted, 200 refused | 0 | 236 ms / 508 ms |

A real morning rush (500 people over 15–30 minutes) is far lighter than the 15-second test. The double-tap test
proves that a person can never be checked in twice, even when two requests arrive at the very same moment. Google
Cloud (Phase 18) adds more API copies automatically under load.

```powershell
cd D:\claude\attendance-system\backend
.\.venv\Scripts\python scripts\load_test.py                                   # 500 in 2 minutes
.\.venv\Scripts\python scripts\load_test.py --employees 500 --window 15 --concurrency 100
.\.venv\Scripts\python scripts\load_test.py --employees 200 --window 10 --double-tap
```
Each run ends with `RESULT: PASS` (no errors, 95% of requests under 1 second) or `FAIL`.

## Automatic testing on GitHub (from Phase 18)

`.github/workflows/ci.yml` runs on every change pushed to GitHub:
- **Backend:** a fresh PostgreSQL 18 with the same roles, migrations and all tests. It fails if code coverage drops
  below 90%. It also runs a small load test and a double-tap test.
- **Dashboard:** type check, tests and production build.
- **App:** `flutter analyze` and tests.

It starts working once the code is on GitHub; until then it does nothing.

## Coverage reports yourself

```powershell
cd D:\claude\attendance-system\backend
.\.venv\Scripts\python -m pytest --cov=app --cov-report=html     # open htmlcov\index.html
cd D:\claude\attendance-system\dashboard
npx.cmd vitest run --coverage                                    # open coverage\index.html
cd D:\claude\attendance-system\mobile
flutter test --coverage                                          # coverage\lcov.info
```
