# Phase 2 — PostgreSQL Database

## What was built

| Item | Where |
|---|---|
| 31 tables as Python models (SQLAlchemy) | `backend/app/models/` |
| Migration 0001: creates all tables, keys, indexes, checks | `backend/alembic/versions/0001_initial_schema.py` |
| Migration 0002: write-once tables, audit hash chain, app-role permissions | `backend/alembic/versions/0002_db_protection.py` |
| Role + database creation script | `database/setup/create_local_databases.sql`, run by `infrastructure/local/setup-local-db.ps1` |
| Demo data | `backend/app/seeds/dev_seed.py` |
| 18 automated tests | `backend/tests/db/test_schema.py` |
| Local settings (generated passwords, never committed) | `backend/.env` |

### Two database accounts

| Role | Used by | Rights |
|---|---|---|
| `attendance_owner` | migrations, future maintenance jobs | owns all tables |
| `attendance_app` | the API (Phase 3+) and the seed | read/write normal tables; **INSERT only** on evidence tables; cannot change the schema |

### Tables

| Group | Tables |
|---|---|
| Organization | `organizations`, `branches`, `locations`, `departments`, `work_schedules`, `work_schedule_days`, `holidays` |
| People | `users`, `employees`, `managers`, `employee_locations`, `leave_records` |
| Auth & devices | `refresh_tokens`, `device_registrations` |
| Attendance | `attendance` (daily summary), `attendance_sessions` (each in/out pair), `attendance_events` (every attempt), `attendance_verification` (signals), `verification_signals` (QR/NFC/BLE/selfie), `attendance_event_reviews`, `attendance_adjustments`, `attendance_challenges` (nonces), `attendance_policies` |
| QR | `qr_sessions` |
| Security & audit | `security_events`, `audit_logs` |
| Reports & notifications | `report_settings`, `report_runs`, `notification_settings`, `notifications`, `retention_settings` |

### Protections enforced by the database itself

- **Write-once evidence:** `attendance_events`, `attendance_verification`, `verification_signals`, `attendance_event_reviews`, `attendance_adjustments`, `security_events` and `audit_logs` reject UPDATE, DELETE and TRUNCATE, even from the table owner. The only exception is the future data-retention job, which must explicitly switch on `app.allow_purge` and run as the owner.
- **Tamper-evident audit log:** each row stores a SHA-256 hash of its contents plus the previous row's hash, so editing any old row breaks the chain.
- **One phone, one employee:** a phone fingerprint can be pending or active for only one employee.
- **One open session per employee**, **one daily summary per employee per day**, **no duplicate request IDs**, case-insensitive unique emails, and range checks on coordinates, radius, accuracy and thresholds.

### Demo data

| What | Detail |
|---|---|
| Company | Demo Company Ltd |
| Offices | Lagos, Abuja, Port Harcourt, Onitsha, Enugu and Uyo. Radius 200 m, timezone Africa/Lagos. **Coordinates are approximate city points; replace them with the real office locations.** |
| Schedule | 09:00–18:00, Monday–Saturday, 15 minutes' grace |
| Departments | HR, Finance, Operations, Sales, IT |
| Users | `admin@example.com`, `hr@example.com`, `manager.lagos@example.com`, `manager.abuja@example.com`, and `emp0101@example.com` to `emp0110@example.com`. EMP-0103 is allowed at both Lagos and Abuja. |
| Password for all demo users | the `SEED_DEFAULT_PASSWORD` value in `backend/.env` |
| Holidays | fixed-date Nigerian public holidays for 2026–27. **Easter and Eid must be added by HR each year.** |
| Rules | every failed check is FLAGGED; flagged events don't count until HR approves; GPS-only for now (switch to GPS + QR once the screens are installed) |
| Reports | daily at 09:30 (Mon–Sat), weekly on Monday at 08:00, monthly on the 1st |
| Retention | attendance and audit 7 years, raw locations 1 year, security events 2 years, report files 90 days |

## How to run it (on your PC)

All commands are run in **PowerShell**.

**1. Create the roles and databases** (one time; asks for your `postgres` password):

```powershell
powershell -ExecutionPolicy Bypass -File "D:\claude\attendance-system\infrastructure\local\setup-local-db.ps1"
```

Expected last line: `Local databases are ready.`

**2. Go to the backend folder:**

```powershell
cd D:\claude\attendance-system\backend
```

**3. Create the tables:**

```powershell
.\.venv\Scripts\alembic upgrade head
```

Expected: two lines, `Running upgrade -> 0001` and `Running upgrade 0001 -> 0002`.

**4. Load the demo data:**

```powershell
.\.venv\Scripts\python -m app.seeds.dev_seed
```

Expected: `Seeded 'Demo Company Ltd': 6 locations, 5 departments, 14 users ...`

**5. Run the tests:**

```powershell
.\.venv\Scripts\python -m pytest
```

Expected: `18 passed`.

### Look at the data (optional)

Open **pgAdmin 4** from the Start menu → Servers → PostgreSQL → enter your `postgres` password → Databases → `attendance_dev` → Schemas → public → Tables. To view rows, right-click a table → View/Edit Data → All Rows.

## Troubleshooting

| Error | Cause / fix |
|---|---|
| `password authentication failed for user "postgres"` (step 1) | Wrong `postgres` password. Check the keyboard language (ENG) and Caps Lock. If you've lost it, run `reset-postgres-password.ps1` in the same folder from an **Administrator** PowerShell. |
| `password authentication failed for user "attendance_owner"` (step 3) | `backend\.env` was changed after step 1. Run step 1 again; it updates the passwords. |
| `connection refused` / `could not connect` | The PostgreSQL service is stopped. Press Win+R, type `services.msc`, and start `postgresql-x64-18`. |
| `.\.venv\Scripts\alembic is not recognized` | You're not in the `backend` folder; do step 2. |
| `running scripts is disabled on this system` | Use the exact `powershell -ExecutionPolicy Bypass -File ...` command from step 1. |
| `already exists - nothing to do` (step 4) | Not an error: the demo data is already loaded. |
| A test fails | Copy the full output and send it to me. |
