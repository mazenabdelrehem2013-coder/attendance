# Phase 7 — Geofence & Location Verification

The server now runs **four** independent checks on every check-in/check-out (Phase 8 adds the rest):

| Check | PASS | WARN (recorded, not a failure on its own) | FAIL → company policy (default **FLAG**) |
|---|---|---|---|
| **Replay** (Phase 6) | one-time code valid | — | code reused / expired / for another phone or action |
| **Geofence** | distance ≤ radius | outside, but **within the GPS uncertainty** (distance − accuracy ≤ radius) | outside even allowing for GPS uncertainty |
| **GPS accuracy** | accuracy ≤ 100 m | accuracy exactly 0 m (never happens with real GPS — typical of fake locations) | accuracy worse than 100 m |
| **Location age** | reading ≤ 60 s old **and** taken after the code was issued | — | older than 60 s, or taken **before** the code was issued (an old reading being reused) |

- **Distance** is calculated by the server with the Haversine formula to every office the employee is assigned to; the office they're "most inside" is used.
- **Two or more WARNs together → FLAGGED** (several small doubts = one real doubt).
- What happens on FAIL is set per company/location in `attendance_policies` (`on_outside_geofence`, `on_poor_accuracy`, `on_stale_location`: `ALLOW` / `FLAG` / `REJECT`), plus `max_accuracy_m` and `max_fix_age_s`. The admin screen for this comes in Phase 12.
- **Messages:** if a check is set to REJECT and the employee can fix it themselves, they're told how — weak signal / old reading → *"Your location signal is weak. Move to an open area or near a window and try again."*; outside → *"You appear to be outside your assigned work location."* Everything else stays general.
- Every decision stores each check's result **and its numbers** (distance, radius, accuracy, reading age, seconds since the code was issued) plus the policy in force, so HR can see exactly why.

## Examples (Lagos office, radius 200 m)

| Phone reports | Result |
|---|---|
| 85 m, accuracy 10 m | ACCEPTED |
| 200 m exactly | ACCEPTED |
| 230 m, accuracy 40 m | ACCEPTED, geofence **WARN** (could be inside) |
| 215 m, accuracy 5 m | FLAGGED (clearly outside) |
| 850 m | FLAGGED (or REJECTED if the policy says so) |
| 20 m, accuracy 150 m | FLAGGED — signal too vague to prove anything |
| 10 m, reading 2 minutes old | FLAGGED — old reading |
| Standing at the Abuja office, assigned only to Lagos | FLAGGED |

## Try it

Same as Phase 6 (`docs/06-attendance.md`, steps 1–7), changing the numbers in the check-in body:

- `"accuracy_m": 150` → `FLAGGED`
- `"fix_age_ms": 120000` → `FLAGGED`
- `"latitude": 6.43017, "accuracy_m": 40` (≈230 m north) → `ACCEPTED`

To see the details, open pgAdmin → `attendance_dev` → `attendance_verification` → View/Edit Data → All Rows: each row shows `geofence`, `gps_accuracy`, `location_age`, `replay_check` and the `details` with the numbers.

Tests:

```powershell
cd D:\claude\attendance-system\backend
.\.venv\Scripts\python -m pytest
```

Expected: `192 passed`.
