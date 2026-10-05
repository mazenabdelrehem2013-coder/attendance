# Phase 19 — Android release on Google Play

## What is ready

| Item | Where |
|---|---|
| App ID (permanent) | `com.raya.attendance`, name **Raya Attendance**, version 1.0.0 (code 1) |
| Signed app bundle for upload | `mobile/build/app/outputs/bundle/release/app-release.aab` (59.5 MB; phones download ~20 MB) |
| Upload key | `D:\claude\keys\raya-attendance-upload.jks` + `key.properties` (password inside). **Back up this folder.** Never in git. |
| Built-in server address | `https://raya.34.35.174.159.nip.io/api/v1` |
| App icon | adaptive (fingerprint on Raya blue), also as Android 13 "themed" icon |
| Store texts | `mobile/store/listing.md` |
| Store graphics | `mobile/store/out/` (icon 512, feature graphic, 4 screenshots) |
| Privacy policy | https://raya.34.35.174.159.nip.io/privacy.html |
| Login for Google's reviewers | employee ID `PLAY-REVIEW` (no workplace: can log in, can't record attendance) |
| Play Integrity on the server | ready but **off** (key for a no-permission service account installed; Google answers "App is not found" until the app exists in your Play Console) |

The release app was tested on Android 15 against the live server: login over HTTPS, phone registration with the
hardware security key (after code shrinking), "waiting for HR approval" screen. The test phone was then rejected.

## Your steps in the Play Console (https://play.google.com/console)

### 1. Create the app
**Create app** → name `Raya Attendance` · default language English · **App** · **Free** · accept the declarations.

### 2. "Set up your app" tasks (Dashboard)
| Task | Answer |
|---|---|
| Privacy policy | `https://raya.34.35.174.159.nip.io/privacy.html` |
| App access | **All or some functionality is restricted** → add instructions: username `PLAY-REVIEW`, password from the command below, text: *"Accounts are created by the employer (Raya HR). This review account has no workplace assigned, so it can log in and register a phone but cannot record attendance. New phones wait for HR approval by design."* |
| Ads | No ads |
| Content rating | Category **Utility, Productivity, Communication or other** → answer No to all content questions |
| Target audience | **18 and over** |
| News app | No |
| Data safety | see the table below |
| Government app / Financial features / Health | No / none / no |

Reviewer password (shown only in your window):
```powershell
& "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" compute ssh tracking --zone africa-south1-b --project gen-lang-client-0101078644 --command "sudo cat /etc/attendance/play-review-password"
```

**Data safety answers**

| Question | Answer |
|---|---|
| Collects or shares user data? | Yes, collects. Encrypted in transit: **Yes**. Users can request deletion: **Yes** (via the contact email) |
| Location → **Precise location** | Collected, **not shared**, required. Purposes: **App functionality**, **Fraud prevention, security and compliance** |
| Personal info → Name, Email address, User IDs, Phone number | Collected, not shared (phone number optional). Purposes: App functionality, Account management |
| App activity → Other actions (check-in/out records) | Collected, not shared. Purpose: App functionality |
| Device or other IDs | Collected, not shared. Purpose: Fraud prevention, security and compliance |
| Photos, videos, contacts, messages, files, health, financial, browsing, audio | **Not collected** (the camera only reads a QR code; nothing is stored) |
| Shared with third parties | **No** |

### 3. Store listing (Grow → Store presence → Main store listing)
Copy texts from `mobile/store/listing.md`, upload the icon, feature graphic and the 4 screenshots, category
**Business**, contact email.

### 4. First release: closed testing
Your developer account is personal: if it was created **after 13 November 2023**, Google requires **12 or more
testers for 14 days in closed testing** before the app can go public.

1. **Test and release → Testing → Closed testing → Create track** (name e.g. "Raya staff").
2. **Testers**: an email list (or a Google Group) with at least 12 people who will really install it (HR, managers…).
3. **Create new release** → Play App Signing: **accept** (Google keeps the final signing key; your upload key is
   replaceable if lost) → upload `app-release.aab` → release name `1.0.0` → notes: "First release" → **Review and roll out**.
4. Share the **opt-in link** shown on the Testers tab; testers open it, accept, and install from Play.

### 5. Link the Google Cloud project (Play Integrity)
**Test and release → App integrity → Play Integrity API → Link a Cloud project** → choose
`gen-lang-client-0101078644` (project number **929211013841**). Then tell me, and I will:
- verify from the server that a real token from a Play-installed app is decoded,
- switch the check on: `sudo bash /opt/attendance/current/server/play-integrity.sh on`.

Only switch it on when everyone installs from Google Play (copies installed any other way would be flagged).

### 6. Going public (after the 14-day test, if it applies to you)
**Dashboard → Apply for production** → answer Google's questions about the test → when approved,
**Production → Create new release** → reuse the same bundle → roll out.

## New versions later

1. Raise the version in `mobile/pubspec.yaml` (e.g. `version: 1.0.1+2` – the number after `+` must increase).
2. Build (runs the app tests first):
   ```powershell
   powershell -ExecutionPolicy Bypass -File D:\claude\attendance-system\mobile\build-release.ps1
   ```
3. Upload `mobile\store\out\raya-attendance-<version>.aab` to the same track.

## Important

- **Back up `D:\claude\keys`** (USB stick / password manager). Without it, new versions need a key reset by Google
  (possible with Play App Signing, takes a few days).
- The server address is built into the app. If the company gets its own domain, a new app version is needed –
  best done before many phones are installed.
