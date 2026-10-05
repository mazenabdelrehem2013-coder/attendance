# Phase 10 — Check-in / Check-out from the App

## What happens when the employee taps CHECK IN

```
1. (if the office requires it) scan the QR code on the office screen
2. location permission + Location turned on?        (asked only now, never in the background)
3. one-time code from the server                     (POST /attendance/challenge)
4. a NEW high-accuracy GPS reading                   (never a cached one)
5. evidence signed inside the phone's secure chip    (Android Keystore, EC P-256)
   (+ Play Integrity token in production)
6. sent to the server -> ACCEPTED / PENDING REVIEW / NOT ACCEPTED, with the server's message
```

The phone **never decides** anything: it sends latitude, longitude, accuracy, reading age, Android's fake-GPS flag and the phone clock; the server does every check (Phases 6–8).

## New in the app

| Feature | Detail |
|---|---|
| Phone registration | Automatic on first launch: creates the hardware key, sends the public key + phone fingerprint. Home shows **"This phone is waiting for HR approval"** until HR approves; the button stays off. Blocked phones are told to contact HR. |
| CHECK IN / CHECK OUT | Progress: *Preparing… → Getting your location… → Verifying…*; then a result card: green **Checked in / Checked out** (time, office, distance), purple **Recorded – pending review**, or red **Not accepted** with the reason the employee may know. |
| Location problems | Location off, permission refused, permission blocked ("Open settings" button), no GPS fix ("move to an open area"). Nothing is sent to the server in these cases. |
| QR offices | If any of the employee's offices requires QR, the app says so and opens the camera scanner first (only accepts office attendance codes). |
| Bad network | The request is resent up to 3 times **with the same request ID** — the server answers with the original result, so nothing is ever recorded twice. No offline check-ins (decision 11.9). |

Native code: `mobile/android/app/src/main/kotlin/.../MainActivity.kt` (Keystore key + signing, ANDROID_ID fingerprint, Play Integrity). Permissions: Location (only while in use), Camera (QR only). Minimum Android version: 8.0.

Backend changes: `/attendance/today` now says whether a QR scan is required (`qr_required`); the phone-clock milliseconds in the signed text are computed exactly (a floating-point rounding could otherwise have rejected a genuine signature).

The signed text format is pinned by the **same example** in a backend test and an app test, so the two can't drift apart.

## Try it on the emulator

1. **Window 1 — API** (as before).
2. **Window 2 — app**:

   ```powershell
   cd D:\claude\attendance-system\mobile
   flutter run
   ```

3. Log in as `EMP-0101`. The home screen shows **"This phone is waiting for HR approval"** (a new registration with this phone's key).
4. Approve it as HR (Swagger: log in as `hr@example.com` → **GET /devices?status=PENDING_APPROVAL** → copy the id → **POST /devices/{id}/approve**). In the app, pull down to refresh → the button turns on.
5. Put the emulator "at the Lagos office": in the emulator click **⋯ (Extended controls) → Location**, enter latitude `6.4283`, longitude `3.4220`, click **Set location**.
6. Tap **CHECK IN** → allow location → **Checked in** with ~25 m from the office point.
7. Set the location to latitude `6.4400` (≈1.3 km away), tap **CHECK OUT** → **Recorded – pending review**.

Tests:

```powershell
flutter test
```

Expected: `All tests passed!` (39 — includes the cross-check of the signed text with the server).

## Troubleshooting

| Problem | Fix |
|---|---|
| Button stays grey | The phone isn't approved yet (step 4), then pull down to refresh. |
| "Location needed" | Allow location when asked; if you chose "Don't allow", tap **Open settings** → Permissions → Location → Allow only while using the app. |
| "We couldn't get your location" | Emulator: set a location in Extended controls → Location. Phone: go outside or near a window. |
| "Not accepted – We couldn't verify this attendance" | Usually the phone key changed (app reinstalled): HR must approve the new registration. |
| Build fails with "Could not resolve…" / network | The first build downloads libraries; check the internet connection and run again. |
