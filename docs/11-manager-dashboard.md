# Phase 11 — Manager Dashboard (web)

## What was built

**Backend**

| Endpoint | Who | What |
|---|---|---|
| `GET /api/v1/manager/attendance?date=&q=&department_id=&location_id=&status=` | Manager (own team) · HR/Admin (everyone) | One row per employee for that day + summary counts |
| `GET /api/v1/manager/attendance/export.csv` (same filters) | same | CSV download (opens in Excel); every export is in the audit log |

Every employee in scope gets a row — also those who never checked in. Their status is worked out from the calendar: **On leave**, **Holiday**, **Day off** (e.g. Sunday), **Not checked in** (working day still running) or **Absent** (working day over). A session still open from a previous day shows **Missing check-out**. The CSV export protects against spreadsheet formula injection (a name like `=HYPERLINK(...)` is written as text).

**Dashboard** (`dashboard/`, React + TypeScript + Material UI)

- Login page (managers, HR, admins; employees are told to use the mobile app), forced password change, change password, log out.
- **Summary cards**: Employees · Present · Late · Absent · Checked in now · Missing check-out · Suspicious (pending review) · On leave. **Click a card to filter the table.**
- **Filters**: date, search (name / employee ID), department, location, status.
- **Table**: Employee · Employee ID · Department · Location · Check-in · Check-out · Working hours · Status (+ checked in / left early / missing check-out) · Verification.
- **Export CSV** button; today's view refreshes itself every minute.
- Security: access token only in memory, refresh token in an HttpOnly cookie (scripts can't read it); expired session → back to login with an explanation; same address as the API (no cross-site requests).

Managers **cannot change anything** here — the dashboard is read-only for them. Left menu items for HR/Admin come in Phase 12.

## Run it

Three windows... or two if the phone app isn't needed.

**Window 1 — API** (as before):

```powershell
cd D:\claude\attendance-system\backend
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

**Window 2 — dashboard** (first time: `npm.cmd install` downloads the libraries, ~1–2 minutes):

```powershell
cd D:\claude\attendance-system\dashboard
npm.cmd install
npm.cmd run dev
```

Open **http://localhost:5173** and log in as:

| Account | Sees |
|---|---|
| `manager.lagos@example.com` | Tunde Bakare's 7 people |
| `manager.abuja@example.com` | Aisha Bello's 3 people |
| `hr@example.com` | all 13 employees |

(password = `SEED_DEFAULT_PASSWORD` from `backend\.env`)

Try: click **Absent**, change the date to an earlier day, search "Emeka", **Export CSV** and open the file in Excel.

## Tests

```powershell
cd D:\claude\attendance-system\dashboard
npm.cmd test
```

Expected: `Tests 13 passed`. Backend: `252 passed`.

## Troubleshooting

| Problem | Fix |
|---|---|
| Page loads but login says "Can't reach the server" | The API (window 1) isn't running. |
| `npm` is not recognized | Node.js is installed; close and reopen PowerShell. |
| `npm.ps1 cannot be loaded because running scripts is disabled` | Windows blocks the `npm` shortcut script. Type `npm.cmd` instead of `npm` (all commands above already do). |
| Port 5173 in use | Vite picks the next free port automatically — use the address it prints. |
| A manager sees nobody | That manager has no employees assigned (HR sets the manager in each employee's record). |
