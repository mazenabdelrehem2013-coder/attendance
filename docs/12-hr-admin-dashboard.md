# Phase 12 — HR / Admin Dashboard

Log in as **HR** (`hr@example.com`) or **Admin** (`admin@example.com`) to get the full menu. Managers keep their team view (Phase 11).

| Menu | What HR/Admin can do |
|---|---|
| **Dashboard** | Today's numbers for the whole company (employees, present, late, absent, checked in, missing check-out, **suspicious attempts**, **rejected attempts**, **waiting for review**) + charts: attendance by location, by department, late arrivals & absences (30 days), monthly attendance rate. Click a number to jump to the details. |
| **Attendance** | The full table with filters and CSV export (same as the manager view, for everyone). |
| **Suspicious activity** | **Review queue**: every flagged check-in/out with the real reason ("Fake-GPS app detected", "Outside the office radius – 872 m"…). Click one to see all 10 checks with their numbers, the phone, the rules in force and a map link. **Approve** → it counts (at the original time). **Reject** (reason required) → it doesn't. Tabs for reviewed items, rejected attempts and security events. |
| **Employees** | Add (temporary password shown once), edit, change role/department/manager/status, check-in locations, reset password. |
| **Locations & departments** | Offices (coordinates, radius, timezone, working hours, on/off), departments, working hours per weekday (grace, early leave), branches (admin only). |
| **Phones** | Approve / reject new phones; switch off a phone. Badge shows how many are waiting. |
| **QR screens** | Register an office screen → a one-time screen key. On the screen open `http://<dashboard>/qr-display`, enter the key: it shows the QR code that changes every 30 s. |
| **Holidays & leave** | Holidays (all offices or one), leave per employee (no overlaps), cancel. |
| **Security settings** | Company-wide rules and per-office rules: GPS only / **GPS + QR**; for each failed check **Allow / Flag / Reject**; limits (GPS accuracy, reading age, travel speed, clock difference). |

The bell at the top shows how many reviews and phones are waiting.

## Review rules

| HR decision | Effect |
|---|---|
| Approve a flagged **check-in** | The session counts from the original check-in time |
| Reject a flagged **check-in** | The session never counts; the employee may check in again |
| Approve a flagged **check-out** | The hours count |
| Reject a flagged **check-out** | The arrival counts, the hours don't (shows "missing check-out") |

- HR **can't review their own** attendance (another HR person or an admin must).
- Each attempt is reviewed **once**; the decision, reviewer and note are kept, and the original evidence is never changed.
- Every review and every settings change is in the audit log (old → new values).

## New backend endpoints

`GET /hr/overview`, `GET /hr/trend`, `GET /hr/attendance`, `GET /hr/review`, `GET /hr/review/{id}`, `POST /hr/review/{id}`, `GET /security-events`, `GET /settings/attendance-policies`, `PUT /settings/attendance-policies/default`, `PUT|DELETE /settings/attendance-policies/locations/{id}`.

## Run it

```powershell
cd D:\claude\attendance-system\backend
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

```powershell
cd D:\claude\attendance-system\dashboard
npm.cmd install
npm.cmd run dev
```

Open http://localhost:5173, log in as `hr@example.com` (password = `SEED_DEFAULT_PASSWORD` in `backend\.env`).

Things to try:
1. **Suspicious activity** → click a row → **Approve** one, **Reject** another with a note. Check **Attendance** for that person.
2. **Security settings** → *Rules for: Lagos Office* → "Outside the office radius" = **Reject** → Save. Check in from far away with the app or the phone simulator → rejected.
3. **QR screens** → Add screen for Lagos → copy the key → open http://localhost:5173/qr-display in another browser window → paste the key → the code changes every 30 s.
4. **Employees** → Add employee → note the temporary password → log in with it in the app → you must choose a new password.

## Tests

```powershell
cd D:\claude\attendance-system\backend
.\.venv\Scripts\python -m pytest
```

Expected `271 passed`.

```powershell
cd D:\claude\attendance-system\dashboard
npm.cmd test
```

Expected `Tests 18 passed`.
