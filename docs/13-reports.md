# Phase 13 — Reports & End-of-Day Job

## End-of-day job

After a day is over, the job finalises it for every employee:

| Situation | Result |
|---|---|
| Checked in, never checked out | Session becomes **Missing check-out** – the arrival counts, no hours |
| Working day, no check-in at all | A stored **Absent** record |
| Leave, holiday, day off (e.g. Sunday), before the hire date | Nothing (never absent) |

Running it twice for the same day changes nothing the second time. Each run is written to the audit log (`DAY_CLOSED`).
In production Cloud Scheduler runs it every night (Phase 18). On your PC:

```powershell
cd D:\claude\attendance-system\backend
.\.venv\Scripts\python -m app.jobs.close_day                    # yesterday
.\.venv\Scripts\python -m app.jobs.close_day --date 2026-10-02  # a given day
```

## Reports

Menu **Reports** in the dashboard (HR/Admin: everyone; managers: only their own team).

| Report | Contents |
|---|---|
| Daily | Employee, ID, department, manager, location, check-in, check-out, working hours, status, verification – plus totals |
| Weekly (Mon–Sun) / Monthly / Custom period | Per employee: **working days, present, absent, late, left early, missing check-out, leave, average check-in, average check-out, average hours, attendance %** – plus totals by **location, department and manager** |
| Employee / location / department / manager | The custom-period report with that filter |
| Late arrivals | Each late day with arrival time and minutes late |
| Absences | Each absent working day |
| Suspicious | Every flagged or rejected attempt with the reason and HR's decision |

Rules used in the numbers:

- **Working day** = a scheduled day that isn't leave, a holiday or before the hire date. **Today counts only once the person has attended** (nobody is absent before the day ends).
- **Attendance %** = present days ÷ working days.
- Flagged days waiting for HR are counted separately (not present, not absent).
- Only the office **name** is shown – never GPS coordinates (privacy).

API: `GET /api/v1/reports/daily | weekly | monthly | period | late | absence | suspicious` with `date`, `month`, `from`/`to` and `location_id`, `department_id`, `manager_id`, `employee_id` filters. Excel/PDF downloads come in Phase 14.

## Try it

1. Close yesterday (window 1, API not needed):

   ```powershell
   cd D:\claude\attendance-system\backend
   .\.venv\Scripts\python -m app.jobs.close_day
   ```

2. Start the API and dashboard as usual, log in as `hr@example.com`, open **Reports** → *Monthly report* → October 2026. Then try *Absences*, *Late arrivals* and a manager login (`manager.lagos@example.com`) to see the team-only version.

## Tests

```powershell
cd D:\claude\attendance-system\backend
.\.venv\Scripts\python -m pytest
```

Expected `285 passed` (includes a full hand-calculated week: present, late, absent, leave, holiday, left early, missing check-out, averages and attendance %).

```powershell
cd D:\claude\attendance-system\dashboard
npm.cmd test
```

Expected `Tests 19 passed`.
