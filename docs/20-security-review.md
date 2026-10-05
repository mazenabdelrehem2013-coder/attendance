# Phase 20 — Final security review (5 October 2026)

Scope: the live system at https://raya.34.35.174.159.nip.io, the server it runs on, the source code (backend,
dashboard, Android app) and the third-party libraries. Checks that change nothing were run against the live
system; nothing was attacked destructively and no real data was touched.

## Result in one line

**No critical or high-risk problem found in the attendance system.** Two weaknesses were fixed during the review;
the remaining items are decisions or tasks listed at the end.

## 1. From the internet (what an attacker sees)

| Check | Result |
|---|---|
| Encryption | TLS 1.3 only; TLS 1.0 / 1.1 refused; valid Let's Encrypt certificate, renews automatically |
| Open ports | only 22 (SSH), 80/443 (web) and 8080 (rewjido). Database (5432) and the API's internal port (8100) are **not reachable** |
| Security headers | HSTS (1 year), Content-Security-Policy (strict for the API, "own files only" for the dashboard), no framing (clickjacking), nosniff, no referrer, no caching |
| Without login | every protected endpoint → 401 |
| Forged tokens | unsigned "ADMIN" token and garbage tokens → 401 |
| Reading server files via path tricks (`../`, encoded `%2e%2e`, `/.env`) | refused (400) or only the dashboard page; no file content |
| Other websites calling the API (CORS) | not allowed |
| TRACE method | 405 |
| Oversized request (3 MB) | 413 (limit 2 MB) |
| API developer pages (`/docs`, `/openapi.json`) | switched off in production |

## 2. Access control (who can do what)

New automatic test `backend/tests/api/test_access_control.py` calls **every one of the 99 API endpoints** as:
nobody (must get 401), an employee and a manager (must be refused anything beyond their role). New endpoints are
included automatically, so a forgotten permission check in the future fails the tests. Result: **no hole**.
Shared lists were confirmed to be limited: an employee sees only their own leave and offices, a manager only their
team (employees list, attendance, leave). 229 checks pass.

Earlier phases already test: organisation separation, HR-only and Admin-only actions, phone binding, request signatures,
replay protection, account lock-out, token theft detection, audit-log tamper detection.

## 3. Code review (security-sensitive parts)

| Area | Finding |
|---|---|
| SQL injection | all database access uses parameters; no SQL built from text |
| Secrets in logs | no passwords, tokens, nonces or signatures are logged |
| Passwords | Argon2id (current recommended settings); 10+ characters; 5 wrong tries lock 15 minutes; IP throttling |
| Login tokens | 15-minute access tokens, signed (HS256, algorithm fixed); refresh tokens stored hashed, rotate on use, reuse ends the session family |
| Dashboard | access token only in memory; refresh token in an HttpOnly, Secure, SameSite=Strict cookie; no `eval`/raw HTML |
| Android app | tokens in Android encrypted storage; phone key in the hardware Keystore; backups off; only the launcher exported; plain-HTTP allowed only in development builds |
| Excel exports | formula injection blocked (`=`, `+`, `-`, `@` prefixed) |
| Error messages | generic for unexpected errors (no stack traces); employees are not told which security check fired |

## 4. The server (read-only inspection)

| Check | Result |
|---|---|
| SSH | keys only (passwords off), root login off. ~1,150 automated login attempts per day from bots, all failing (normal on the internet) |
| Updates | automatic security updates on; 6 ordinary updates waiting; no reboot pending |
| Database | listens only inside the server; SCRAM-SHA-256 passwords; both app accounts are **not** superusers; API account cannot delete/alter evidence |
| Secrets | `/etc/attendance` readable only by root and the service; backups root-only |
| Services | own user `attendance`; systemd sandbox (exposure 4.7 "OK"); memory limits |

## 5. Libraries (known vulnerabilities)

| Part | Result |
|---|---|
| Dashboard (npm audit) | 0 |
| Backend runtime (59 packages, OSV.dev) | 0 |
| Android app (89 packages, OSV.dev) | 0 |
| Test tools | **pytest 8.4.2** has a temp-folder issue (fixed in 9.0.3). Used only for tests on the PC/GitHub, never installed on the server. Recommended update. |

## 6. Fixed during this review

| # | Problem | Risk | Fix |
|---|---|---|---|
| F1 | The app's own user could **write to its code folder** (packing on Windows kept write permissions) | Low (the running service's sandbox already makes the disk read-only) – but a weak second line | `deploy.sh` now sets code to read-only for the app; redeployed and verified |
| F2 | No general limit on request rate per address (only failed logins were throttled) | Medium (floods could slow the API) | nginx limit: 20 requests/s per address, bursts up to 200 (an office behind one address is far below). Tested: excess gets 429, normal use continues |

## 7. Open items

### For you (Raya)
| Priority | Item |
|---|---|
| **High** | **Log in as admin and change the temporary password** – the admin account has never been used. Then `sudo rm /etc/attendance/initial-admin-password`. |
| **High** | **Back up `D:\claude\keys`** (Play upload key). |
| High | Before real employees use it: switch **Play Integrity on** once the app is installed from Google Play (Phase 19 step 5). |
| Medium | **Off-server backup copy** (Google Cloud Storage in Johannesburg, a few cents/month). Today backups are on the same server. |
| Medium | Monitoring: Google uptime check + alert e-mail to you (free). |
| Medium | Own domain (e.g. `attendance.raya.com`) – before many phones are installed (the address is built into the app). |
| Low | Update pytest to 9.0.3 (test tool only). |
| Low | Retention periods: confirm with a lawyer (NDPA 2023). |

### On the shared server (not part of the attendance system – your decision)
| Item | Note |
|---|---|
| CargoTrace (port 4000) and rewjido (port 4100) listen on **all** network interfaces | Protected today only by the Google firewall; binding them to 127.0.0.1 would add a second line |
| CargoTrace service runs without sandboxing (exposure 8.5) | Could get the same systemd hardening as attendance |
| CargoTrace admin still uses the seeded default password (noted in its own records) | Change it |
| SSH: X11 forwarding on; no fail2ban | Low risk with key-only SSH; can be tightened |

## How to repeat the checks

```powershell
cd D:\claude\attendance-system\backend
.\.venv\Scripts\python -m pytest tests\api\test_access_control.py
cd D:\claude\attendance-system\dashboard
npm.cmd audit
```
