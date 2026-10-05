# Phase 16 — Audit log, security monitoring, data retention

New HR/Admin menu items: **Security monitoring** (red badge = open alerts) and **Audit log**.

## Audit log

Every change in the system (employees, locations, phones, reviews, settings, reports downloaded...) with **who,
when, from which address, and the old → new values**. Filter by dates, action or person; click a row to see
"Before / After". **Export Excel** downloads up to one year of entries; the export itself is recorded.

### Tamper check

Each audit entry carries a fingerprint (hash) that includes the previous entry's fingerprint, so the entries form a
chain. Every night after 02:00 (and when someone clicks **Check now**), the system recomputes the whole chain:

| What someone did directly in the database | How it shows |
|---|---|
| changed an entry | "Entry #N was changed after it was written" |
| deleted an entry in the middle | "Entries before #N were deleted" |
| deleted the newest entries | "Entries from #N (already verified) were deleted" |

The result is shown at the top of both pages (green = intact, red = tampering). If the chain is broken, a
**CRITICAL** alert is raised. The database itself already refuses changes and deletions (Phase 2). This check also
catches someone who switches that protection off.

## Security monitoring

- **Overview** (last 30 days): open alerts, security events per day by severity, failed logins, locked accounts,
  most frequent events, employees with the most serious events, and the internet addresses with the most failed logins.
- **Alerts**: raised automatically by the rules below, checked every minute. New alerts appear under the bell for
  HR and Admin. Press **I'm checking it**, then **Resolve** with a note (required). Every step goes into the audit log.
  After an alert is resolved, a new one appears only if new events happen.
- **Alert rules**:

| Rule | Severity | Raised when |
|---|---|---|
| Account locked | High | an account is locked after 5 wrong passwords |
| Many failed logins from one address | High | 20+ failed logins from one internet address in 15 minutes |
| Possible stolen session | High | a login token was used twice (the session is ended automatically) |
| Phone used by two employees | High | someone tries to register another employee's phone |
| Repeated fake location or tampering | High | 3+ fake-GPS / modified-app / bad-signature / copied-request events by one employee in 24 h |
| Unusual number of suspicious check-ins | Medium | 15+ check-in security events company-wide in one hour |
| Audit log tampering | Critical | the tamper check fails |

Each alert is also written to the server log as `SECURITY_ALERT`, so Google Cloud can e-mail or text the
administrator (set up in Phase 18).

## Data retention

Security monitoring → **Data retention**. Old data is removed every night. Only an **Admin** can change the periods.
HR can view them.

| Data | Default | After that |
|---|---|---|
| Attendance records | 7 years | kept (never deleted automatically) |
| GPS coordinates | 1 year | coordinates removed; distance to the office, result and time stay |
| Security events | 2 years | deleted |
| Audit log | 7 years | oldest entries deleted (the rest of the chain stays verifiable) |
| Bell alerts | 180 days | deleted |
| Ready report files | 90 days | deleted |

These are the recommended defaults from the architecture (decision 11.13). Check them against Nigerian labour
and data-protection rules (NDPA 2023), and change them if your lawyer advises otherwise.

**How deletion stays safe:** the API's own database account cannot delete or change attendance, audit or security
data at all. Only the database owner account, used by the nightly job, can. Even that account can only
remove these items after switching on a special setting for that single operation. For GPS coordinates it can
change nothing except those three columns, and the database checks this.

## Try it

```powershell
cd D:\claude\attendance-system\backend
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```
(`upgrade head` was already run on your dev database.)

```powershell
cd D:\claude\attendance-system\dashboard
npm.cmd run dev
```

1. http://localhost:5173 → log in as `hr@example.com` → **Audit log**: you see today's changes; click one; press
   **Check now** → green "Audit log intact".
2. **Security monitoring**: the overview with your test data.
3. To see an alert: in a private browser window, log in as `manager.lagos@example.com` with a wrong password
   5 times → within a minute, **Security monitoring → Alerts** shows "Account locked", the bell shows a security
   alert. Resolve it with a note. (The account unlocks by itself after 15 minutes.)
4. Log in as `admin@example.com` → Security monitoring → **Data retention**: the periods can be edited.

## Tests

```powershell
cd D:\claude\attendance-system\backend
.\.venv\Scripts\python -m pytest
```
Expected **`354 passed`**. 17 are new: tamper detection of changed, deleted-middle and deleted-newest entries,
every alert rule, and retention including the GPS-only clearing.

```powershell
cd D:\claude\attendance-system\dashboard
npm.cmd test
```
Expected **`Tests 32 passed`**.
