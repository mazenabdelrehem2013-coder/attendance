# Phase 15 — Scheduled reports, downloads in the app, alerts

No emails are sent. Reports are downloaded from the **web dashboard** and from the **Android app**.

## What it does

| Feature | Who | Where |
|---|---|---|
| **Create a report now** (daily, weekly, monthly, date range, late, absences, suspicious) as Excel or PDF | Managers (own team), HR (everyone) | Dashboard → Reports → *Create a report*; App → 📊 Reports → *Create a report* |
| **Scheduled reports**: created automatically, e.g. every Monday 08:00 | HR sets them up | Dashboard → **Scheduled reports** |
| **Ready reports**: the files made by schedules, kept 90 days | HR: company-wide files · each manager: their own team's files | Dashboard → Reports → *Ready reports*; App → Reports → *Ready reports* |
| **Alerts** (bell icon in the dashboard) | HR and managers | Dashboard top bar; settings: Scheduled reports → *Alerts* |

Employees never see reports in the app: the Reports button appears only for managers, HR and admins (and the server
refuses everyone else anyway). HR/Admin accounts without an employee record open straight into the Reports screen.

### In the app

- Files are saved in the phone's **Downloads/Attendance** folder (Android 10 and newer, no permission needed), then
  **OPEN** shows them in Excel / Google Sheets / a PDF viewer.
- On Android 8–9 the file opens straight away (from there it can be saved or shared).

Screenshots: `docs/screenshots/phase15-app-*.png`.

### Alerts (defaults, changeable by HR)

| Alert | Who sees it |
|---|---|
| Check-in needs review (flagged) | HR |
| Check-in rejected (once per employee per day) | HR |
| New phone waiting for approval | HR |
| Late arrival (once per employee per day) | the employee's manager |
| Missing check-out (end-of-day job) | the employee's manager |
| Frequent absence (3 in 30 days, changeable) | HR + manager |
| Scheduled report ready | HR + managers it was made for |

### Safety

- Each scheduled time is created **once only**, even if two servers run the scheduler at the same time (database lock).
- A schedule more than 6 hours late (server was off) is skipped instead of created late.
- A manager can only list and download their own team's files; asking for another file gives "not found".
- Every download is in the audit log (`REPORT_DOWNLOADED`), as are schedule changes and alert-setting changes.
- Files older than `REPORT_FILES_KEEP_DAYS` (90) are deleted automatically.

## The scheduler

`RUN_SCHEDULER_IN_API=true` (in `backend\.env`) makes the API run it every minute. Each run:
1. closes yesterday (missing check-outs, absences, their alerts) after 00:15,
2. creates the scheduled reports that are due,
3. deletes old report files.

By hand: `.\.venv\Scripts\python -m app.jobs.scheduler` (once) or `... --loop`.
In Google Cloud (Phase 18), Cloud Scheduler runs it every 5 minutes.

## Try it

1. Update the database and start the API (window 1):
   ```powershell
   cd D:\claude\attendance-system\backend
   .\.venv\Scripts\python -m alembic upgrade head
   .\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
   ```
   (Already done on your dev database; it prints nothing new.)
2. Dashboard (window 2):
   ```powershell
   cd D:\claude\attendance-system\dashboard
   npm.cmd run dev
   ```
   http://localhost:5173 → log in as `hr@example.com` → **Scheduled reports** → **Create now** on a schedule →
   **Reports → Ready reports** → **Download**.
3. App: install the new version (Phase 10 steps: `flutter run` with the emulator open), log in as
   `manager.lagos@example.com` → tap 📊 (top right) → **DOWNLOAD** → **OPEN**.

## Tests

```powershell
cd D:\claude\attendance-system\backend
.\.venv\Scripts\python -m pytest
```
Expected **`337 passed`**.

```powershell
cd D:\claude\attendance-system\dashboard
npm.cmd test
```
Expected **`Tests 25 passed`**.

```powershell
cd D:\claude\attendance-system\mobile
flutter test
```
Expected **`All tests passed!`** (45 tests).

## Troubleshooting

| Problem | Fix |
|---|---|
| No Reports button in the app | the account is an employee; only managers / HR / admins get it |
| "No app on this phone can open this file" | install Google Sheets / Excel (for .xlsx) or use PDF |
| Ready reports is empty | schedules create files at their time; use **Create now** to test |
| A schedule didn't run | check "Next" on the Scheduled reports page and that the API is running (`RUN_SCHEDULER_IN_API=true`) |
