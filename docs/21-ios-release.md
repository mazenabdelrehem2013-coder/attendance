# Phase 21 — iOS release on the App Store

The iPhone app is the same Flutter app as on Android. It is built and signed in the cloud by
**Codemagic** (`codemagic.yaml` in the repository root), so no Mac is needed. GitHub Actions also
compiles it (unsigned) on every push, in the `mobile-ios` job of `.github/workflows/ci.yml`.

## What is ready

| Item | Where |
|---|---|
| Bundle ID (permanent) | `com.raya.attendance`, name **Raya Attendance**, version from `pubspec.yaml` (1.0.0) |
| Devices | iPhone only (iOS 15+); no iPad version, so no iPad screenshots are needed |
| App icon | `mobile/ios/Runner/Assets.xcassets/AppIcon.appiconset` (fingerprint on Raya blue), made by `mobile/store/make_ios_icons.py` |
| Permission texts | location (only while checking in/out) and camera (office QR code), in `mobile/ios/Runner/Info.plist` |
| Encryption answer | `ITSAppUsesNonExemptEncryption = NO` (HTTPS and standard signing only), so no export-compliance question per build |
| Phone security | EC P-256 key in the Secure Enclave, same signature format as Android; phone ID kept in the keychain |
| Reports | saved in the Files app under *On My iPhone › Raya Attendance › Attendance*, opened in Apple's preview |
| Built-in server address | `https://raya.34.35.174.159.nip.io/api/v1` (`API_BASE_URL` in `codemagic.yaml`) |

### Difference from Android: no Play Integrity
Google Play Integrity exists only on Android. iPhones register as platform `ios` (HR sees this in
the phone list) and send no integrity token. The server is unchanged, so with
`PLAY_INTEGRITY_MODE=google` iPhone check-ins get the **"No integrity token"** flag for HR review
(the default policy flags, it does not reject). Apple's equivalent, App Attest, can be added
later on both the app and the server.

## Your steps

### 1. Apple Developer Program
Enrol at https://developer.apple.com/programs/ (99 USD per year). Enrol as an **organization**
if the app should be published under the company name (needs a D-U-N-S number).

### 2. Create the app in App Store Connect (https://appstoreconnect.apple.com)
1. **Certificates, Identifiers & Profiles › Identifiers ›** register the App ID
   `com.raya.attendance` (no extra capabilities needed).
2. **Apps › + › New App**: platform iOS, name `Raya Attendance`, primary language English,
   bundle ID `com.raya.attendance`, SKU e.g. `raya-attendance`.

### 3. API key for Codemagic
**Users and Access › Integrations › App Store Connect API › +**, role **App Manager**. Download
the `.p8` file (only possible once) and note the **Issuer ID** and **Key ID**.

### 4. Codemagic (https://codemagic.io, free tier is enough)
1. Sign in with GitHub and add the `attendance` repository.
2. **Team settings › Integrations › Developer Portal › Manage keys › Add key**: name it exactly
   `Raya App Store Connect`, paste the Issuer ID and Key ID, upload the `.p8`.
3. **Certificate private key** (once): make a 2048-bit RSA key, e.g.
   `ssh-keygen -t rsa -b 2048 -m PEM -f ios_distribution_private_key -q -N ""`. In Codemagic ›
   the app › **Environment variables**, add `CERTIFICATE_PRIVATE_KEY` with the whole file
   (including the `BEGIN`/`END` lines), group `code-signing`, **Secret** ticked. On the first
   build Codemagic creates the Apple Distribution certificate for this key and the App Store
   profile; later builds reuse them. Keep a copy of the key: a new key means a new certificate,
   and Apple allows only 3.
4. **Start new build** › branch `main` › workflow **iOS release (App Store)**. The result is a
   signed `Runner.ipa` under the build's artifacts. Nothing is sent to Apple yet.

### 5. Send a build to Apple (only when you decide)
Uncomment the `publishing:` block at the end of `codemagic.yaml` and run the build again: it
uploads to App Store Connect and TestFlight. Then, in App Store Connect, fill in the listing and
press **Submit for Review**.

## The listing in App Store Connect

| Field | Value |
|---|---|
| Texts | reuse `mobile/store/listing.md` (subtitle max 30 characters) |
| Privacy policy URL | `https://raya.34.35.174.159.nip.io/privacy.html` |
| Category | Business |
| Age rating | answer "None" to everything (4+) |
| App Privacy | Data collected and linked to the user, not used for tracking: **Precise location** (app functionality), **Name / User ID** (app functionality), **Device ID** (app functionality / security) |
| Screenshots | 6.9" iPhone, 1320 × 2868 (or 6.5", 1284 × 2778), 3 to 10 images, taken from an iPhone or the iOS simulator; Android screenshots are refused |
| Sign-in for review | an account that can log in **and** check in (see below) |

### App Review notes
- Apple reviewers must be able to use the main feature. The `PLAY-REVIEW` account (no workplace)
  is likely to be refused under guideline 2.1. Give them an employee with a workplace whose
  verification mode is GPS only and a large radius, or explain in the notes why they can't be
  at the office, and send a short screen recording of a check-in.
- An app only for one company's employees can be refused under guideline 3.2 ("business app
  for a specific organization"). If that happens, ask for **Unlisted App Distribution**
  (https://developer.apple.com/support/unlisted-app-distribution/): same App Store, found
  only through a link.
