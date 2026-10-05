# Phase 8 — Anti-Spoofing & Security Verification

Every check-in/check-out now passes through **ten independent checks**. No single one is trusted on its own; together they make faking attendance hard and — above all — **visible to HR**.

| # | Check | Catches | Can't catch on its own | On failure |
|---|---|---|---|---|
| 1 | **One-time code** (Phase 6) | replayed / copied requests | — | REJECT |
| 2 | **Phone signature** (new) | stolen login used from another phone or a script; any field changed after the phone signed it | the real phone in the wrong hands | **always REJECT** |
| 3 | **Geofence** (Phase 7) | being elsewhere | faked coordinates | policy (FLAG) |
| 4 | **GPS accuracy** (Phase 7) | vague, network-only positions; 0 m accuracy (fake-GPS hint) | precise fakes | policy (FLAG) |
| 5 | **Location age** (Phase 7) | old readings being reused | — | policy (FLAG) |
| 6 | **Mock location** (new) | most "Fake GPS" apps (Android marks their locations) | rooted phones that hide the mark | policy (FLAG) |
| 7 | **Play Integrity** (new) | modified/re-signed app, not installed from Play, emulators, many rooted phones; token reused for another request | well-hidden rooting on some phones | policy (FLAG) |
| 8 | **Phone clock** (new) | clock changed by hand (> 5 min off) | — | policy (FLAG) |
| 9 | **Impossible movement** (new) | Lagos 09:00 → Abuja 09:15 (≈2,100 km/h; limit 200 km/h, GPS uncertainty subtracted) | a fake that always reports the same spot | policy (FLAG) |
| 10 | **Rotating office QR** (new, when the location requires it) | being somewhere else entirely; a shared photo of the code (expires in ≤ 60 s) | a colleague sending a *live* photo — but GPS must still match | policy (FLAG) |

- **Employees are never told which check fired** ("waiting for HR review" / "couldn't verify — contact HR"). Only weak-signal and outside-location rejections say how to fix them.
- **Every failure creates a security event** for HR: `MOCK_LOCATION`, `INTEGRITY_FAIL`, `BAD_SIGNATURE`, `IMPOSSIBLE_TRAVEL`, `CLOCK_SKEW`, `QR_INVALID`, `QR_MISSING`, `OUTSIDE_GEOFENCE`, `REPLAY`, `DEVICE_SHARED`.
- If Google's integrity service is down, the employee isn't punished — it's recorded as a warning.

## Phone keys

At registration the app creates a key pair inside the phone's secure hardware (Android Keystore); only the public half is sent to us. Every request is signed. If an approved phone suddenly presents a **different** key (app reinstalled — or an imposter), the old registration stops working and HR must approve the new one.

The exact text the phone signs is defined in `backend/app/services/attendance/canonical.py` (the mobile app in Phase 10 must match it; a test pins the format).

## Office QR screens

| Endpoint | Who | What |
|---|---|---|
| `POST /qr-displays` | HR | Register a screen for a location → returns a **display key** (shown once) |
| `GET /qr-displays` | HR | Screens, their location and last contact |
| `POST /qr-displays/{id}/rotate-key` | HR | New display key — old key and all old codes stop working (e.g. tablet stolen) |
| `POST /qr-displays/{id}/disable` · `/enable` | HR | |
| `GET /qr/current` + header `X-Display-Key` | the office screen | The code to show now (changes every 30 s) |

To **require** QR at a location, set `verification_mode` = `GPS_QR` in its attendance policy (admin screen in Phase 12). The screen web page that shows the code comes with the dashboard (Phase 12).

## Play Integrity

`PLAY_INTEGRITY_MODE=off` locally (there's no Play Store build yet). In production (Phases 18–19) it's set to `google` and the API verifies every token with Google using the Cloud Run service account — no keys in the app. If production ever runs with it off, the API logs a **CRITICAL** warning at startup.

## Try it — phone simulator

Check-ins now need a cryptographic signature, so they can't be typed into Swagger by hand. Until the real app exists, use the simulator (it registers a simulated phone, gets it approved by `hr@example.com`, signs and sends):

```powershell
cd D:\claude\attendance-system\backend
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

In a **second** PowerShell window:

```powershell
cd D:\claude\attendance-system\backend
.\.venv\Scripts\python scripts\simulate_phone.py EMP-0105 check-in
.\.venv\Scripts\python scripts\simulate_phone.py EMP-0105 check-out
.\.venv\Scripts\python scripts\simulate_phone.py EMP-0105 check-in --mock
.\.venv\Scripts\python scripts\simulate_phone.py EMP-0105 today
```

Other options: `--meters-north 850` (outside), `--accuracy 150` (weak signal), `--old-reading`, `--qr <token>`.
(EMP-0105 works at Abuja — add `--lat 9.0563 --lng 7.4985` for "at the office".)

Tests:

```powershell
.\.venv\Scripts\python -m pytest
```

Expected: `237 passed`.

## Honest limits

No Android app can be made spoof-proof. A determined person with a rooted phone, a tool that hides root from Play Integrity and a precise GPS spoofer that also avoids impossible jumps could still pass GPS-only mode. That's why locations needing high assurance should use **GPS + QR**, and why HR gets a full trail of every doubt.
