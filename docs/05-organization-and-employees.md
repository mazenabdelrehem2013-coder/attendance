# Phase 5 — Organization & Employee Management APIs

## Endpoints

| Endpoint | Who | What |
|---|---|---|
| `GET /branches` · `POST` · `PUT /branches/{id}` | read: Manager/HR · write: **Admin** | Branches |
| `GET /departments` · `POST` · `PUT /departments/{id}` | read: Manager/HR · write: HR | Departments |
| `GET /work-schedules` · `POST` · `PUT /work-schedules/{id}` | read: Manager/HR · write: HR | Working hours per weekday + grace + early-departure minutes |
| `GET /locations` | everyone (employees: only their own) | Locations; `?include_inactive=true` shows disabled ones |
| `GET /locations/{id}` · `POST /locations` · `PUT /locations/{id}` | read: Manager/HR · write: HR | Coordinates, radius (10–5000 m), timezone, schedule, active |
| `GET /employees` | Manager (own team only) / HR | Search `q`, filter by department, location, manager, role, status; pages |
| `GET /employees/{id}` | Manager (own team only) / HR | One employee |
| `POST /employees` | HR | Creates employee **and** login; returns a **temporary password once** |
| `PUT /employees/{id}` | HR | Name, email, phone, department, manager, schedule, role, status, login on/off |
| `PUT /employees/{id}/locations` | HR | Where the employee may check in (+ primary location) |
| `POST /employees/{id}/reset-password` | HR | New temporary password; logs the person out everywhere |
| `GET /managers` | HR | Active managers with team size (for dropdowns) |
| `GET /employees/me` · `PUT /employees/me` | the employee | Own profile; may change **only** their phone number |

ADMIN can do everything HR can. "Write" endpoints use **PUT with only the fields you want to change**; nothing is ever deleted — set `is_active: false` instead.

## Rules enforced

- **Managers see only their own team** — another manager's employee returns `404` (the same as a non-existent one, so nobody can probe for records).
- **Organizations are isolated** — no endpoint shows or changes another company's data.
- **HR can create EMPLOYEE and MANAGER accounts; only ADMIN can create or change HR/Admin accounts** or reset their passwords. Nobody can change their own role or status.
- Making someone `MANAGER` adds them to `/managers`; changing a manager back is refused while they still have a team (`MANAGER_HAS_TEAM`) — reassign the team first.
- Suspending/terminating an employee or turning their login off ends all their sessions immediately.
- New accounts get a temporary password (`Abcd-Efgh-Jkmn` style, no look-alike characters) and must change it at first login.
- Inactive locations can't be assigned; an employee can't be their own manager; duplicate emails/codes → `409`.
- **Every change is in the audit log** with old and new values, who did it, their role, IP and request ID — e.g. `LOCATION_UPDATED {radius_m: 200 → 300}`, `EMPLOYEE_LOCATIONS_CHANGED`, `USER_PASSWORD_RESET` (the password itself is never logged).

Holidays and leave management endpoints come with the attendance rules in Phase 6.

## Try it

1. Start the API (PowerShell):

   ```powershell
   cd D:\claude\attendance-system\backend
   .\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
   ```

2. Open http://localhost:8000/docs, log in as **`hr@example.com`** (password = `SEED_DEFAULT_PASSWORD` from `backend\.env`) with **POST /auth/login**, copy `access_token`, click **Authorize**, paste, close.
3. Try:
   - **GET /employees** → 13 employees.
   - **GET /locations** → copy the `id` of *Lagos Office*.
   - **PUT /locations/{location_id}** → paste the id, body `{"radius_m": 250}` → Execute → `radius_m` is 250.
   - **POST /employees** → body (replace the location id):

     ```json
     {
       "full_name": "Test Person",
       "employee_code": "EMP-0999",
       "email": "test.person@example.com",
       "location_ids": ["PASTE-LAGOS-LOCATION-ID"]
     }
     ```

     → `201` with a `temporary_password`.
4. Log in as **`manager.abuja@example.com`** (Authorize again with its token) → **GET /employees** → only Hauwa Sani, Ibrahim Musa and Tamuno Briggs.
5. See the audit trail in pgAdmin: `attendance_dev` → `audit_logs` → View/Edit Data → All Rows.

6. Tests (second window):

   ```powershell
   cd D:\claude\attendance-system\backend
   .\.venv\Scripts\python -m pytest
   ```

   Expected: `96 passed`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `403 FORBIDDEN` | You're logged in with a role that may not do this (e.g. manager editing, HR creating an HR account). |
| `404 Employee not found` as a manager | That employee isn't in your team — by design. |
| `409 DUPLICATE` | That email, employee ID or location code already exists. |
| `422` with `details` | The `field` named in `details` is invalid (e.g. latitude outside −90…90, radius under 10 m, timezone not like `Africa/Lagos`). |
| `409 MANAGER_HAS_TEAM` | Move that manager's employees to another manager first (`PUT /employees/{id}` with `manager_id`). |
