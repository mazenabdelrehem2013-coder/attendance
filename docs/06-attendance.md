# Phase 6 — Attendance Data & APIs

## How a check-in works

```
Phone                                      Server
  |  POST /attendance/challenge  ------------> one-time code (nonce), valid ~90 s
  |  (then reads GPS)                          (only for an HR-approved phone)
  |  POST /attendance/check-in   ------------> 1. phone approved & belongs to this employee?
  |     evidence + code                        2. code valid, unused, for this phone/action?  (replay check)
  |                                            3. action possible? (not already checked in ...)
  |                                            4. distance to each assigned office (Haversine) -> nearest
  |                                            5. signals -> location policy -> ACCEPTED / FLAGGED / REJECTED
  |  <---------------------------------------- 6. stored (event + every signal) ; result returned
```

- **Time = server time.** The phone's clock is stored as evidence only.
- **The phone never says "I'm inside"** — such a field is refused (`422`). The server measures the distance.
- **Every attempt is stored**, including rejected ones, with all signals and the policy in force.
- **FLAGGED** (e.g. outside the radius — company default) → recorded, *does not count* (no PRESENT, no hours) until HR approves. HR review screen: Phase 12.
- **Several check-in/out pairs per day**; hours are added up; arrival status from the first check-in, departure from the last check-out.
- Same request sent twice (bad network) → same result, never a duplicate. Reusing a code → `REJECTED` + `REPLAY` security event.
- Employees get a general message (e.g. "waiting for HR review"); the exact reason is only visible to HR.

Phase 6 signals: **replay** and **geofence** (distance ≤ radius). Phase 7 adds GPS accuracy (accuracy-aware geofence) and location age; Phase 8 adds mock-location, Play Integrity, impossible movement, clock skew, QR and phone signatures.

## Endpoints

| Endpoint | Who | What |
|---|---|---|
| `POST /devices/register` | employee | Register this phone → `PENDING_APPROVAL` |
| `GET /devices/me` | employee | My phones and their status |
| `GET /devices?status=PENDING_APPROVAL` | HR | Phones waiting for approval |
| `POST /devices/{id}/approve` · `/reject` · `/deactivate` | HR | Decide (approving a new phone switches off the old one) |
| `POST /attendance/challenge` | employee | Step 1: one-time code |
| `POST /attendance/check-in` · `/check-out` | employee | Step 2: evidence → result |
| `GET /attendance/today` | employee | State (`NOT_CHECKED_IN` / `CHECKED_IN` / `CHECKED_OUT`), next action, working hours, day type (working / weekend / holiday / leave), sessions, today's attempts with messages |
| `GET /attendance/history?from=&to=` | employee | Daily records (max 93 days) |
| `GET /holidays?year=` · `POST` · `DELETE /holidays/{id}` | all read · HR write | Holidays (all locations or one) |
| `GET /leave` · `POST /leave` · `POST /leave/{id}/cancel` | HR write; managers see their team, employees their own | Leave (no overlaps) |

## Rules (09:00–18:00, Mon–Sat, 15 min grace)

| Situation | Result |
|---|---|
| First check-in 09:07 | PRESENT |
| First check-in 09:15:00 | PRESENT |
| First check-in 09:15:01 or 09:25 | LATE |
| Last check-out before 18:00 | EARLY_DEPARTURE |
| Sunday / holiday / leave | `day_type` NON_WORKING_DAY / HOLIDAY / ON_LEAVE (working anyway is allowed, never LATE) |
| Times compared in the location's timezone (Africa/Lagos) | |

Database change: migration **0004** (session `pending_review`, session status `REJECTED`).

## Try it

The phone app comes in Phase 9–10; until then you can run the whole flow in Swagger.

1. Start the API:

   ```powershell
   cd D:\claude\attendance-system\backend
   .\.venv\Scripts\python -m pip install -r requirements-dev.txt
   .\.venv\Scripts\alembic upgrade head
   .\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
   ```

2. http://localhost:8000/docs — log in as **`EMP-0101`** and **Authorize** (as before).
3. **POST /devices/register** with:

   ```json
   {"device_fingerprint": "1111111111111111111111111111111111111111111111111111111111111111", "install_id": "swagger-test-1", "device_model": "Test phone"}
   ```

   → `"status": "PENDING_APPROVAL"`. Copy the `id`.
4. **Logout** in Authorize, log in as **`hr@example.com`**, Authorize, **POST /devices/{device_id}/approve** with the id → `ACTIVE`.
5. Log back in as **`EMP-0101`**, Authorize.
6. **POST /attendance/challenge**: `{"action": "CHECK_IN", "device_id": "PASTE-DEVICE-ID"}` → copy `challenge_id` and `nonce`.
7. Within 90 seconds, **POST /attendance/check-in** (paste the three values; any new UUID works for `client_request_id`, e.g. from https://www.uuidgenerator.net):

   ```json
   {
     "client_request_id": "PASTE-A-NEW-UUID",
     "challenge_id": "PASTE",
     "nonce": "PASTE",
     "device_id": "PASTE",
     "latitude": 6.4283, "longitude": 3.4220,
     "accuracy_m": 10, "fix_age_ms": 1500
   }
   ```

   → `"result": "ACCEPTED"`, `"location": "Lagos Office"`, `distance_meters` ≈ 25, and `PRESENT` or `LATE` depending on the time.
8. Try it again with a new challenge but `"latitude": 6.4400` (≈1.3 km away) after checking out → `"FLAGGED"`, "waiting for HR review".
9. **GET /attendance/today** to see the state, sessions and attempts.

Tests:

```powershell
.\.venv\Scripts\python -m pytest
```

Expected: `154 passed`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `403 DEVICE_PENDING_APPROVAL` | HR hasn't approved the phone yet (step 4). |
| `409 DEVICE_IN_USE` | That fingerprint is registered to another employee — use a different 64-character value. |
| Result `REJECTED`, message "This request expired" | The challenge was older than 90 s, already used, or for another action — get a new one (step 6). |
| Result `REJECTED`, "You are already checked in" | Check out first. |
| `422` | A field is missing/invalid (e.g. latitude), or the JSON contains an extra field. |
