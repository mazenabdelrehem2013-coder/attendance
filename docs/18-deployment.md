# Phase 18 — Deployment (free: on the existing CargoTrace server)

## Where everything is

| What | Where |
|---|---|
| **Web address** (dashboard + API) | **https://raya.34.35.174.159.nip.io** (free HTTPS certificate from Let's Encrypt, renews automatically) |
| API address for the phone app (Phase 19) | `https://raya.34.35.174.159.nip.io/api/v1` |
| Server | Google Cloud VM `tracking`, zone `africa-south1-b` (Johannesburg), project `gen-lang-client-0101078644`, shared with CargoTrace and rewjido |
| Server IP | `34.35.174.159`, now **reserved** (name `tracking-ip`) so it never changes |
| Database | PostgreSQL 17 **on the same server**, only reachable from inside it (no open port) |
| Code on the server | `/opt/attendance/current` (the last 5 versions in `/opt/attendance/releases`) |
| Settings and secrets | `/etc/attendance/` (root only; generated on the server, never copied anywhere) |
| Backups | `/var/backups/attendance/` every night at 01:30 (UTC), 14 days kept |
| Source code | private GitHub repository `mazenabdelrehem2013-coder/attendance` (tests run there automatically on every push) |
| Extra cost | **$0** (shared server, free certificate, free address) |

`nip.io` is a free service that turns `raya.34.35.174.159.nip.io` into the IP address. When the company gets its own
domain (e.g. `attendance.raya.com`), only nginx + a new certificate + the app's address change.

## First login (do this now)

1. Read your temporary password (shown only in your own terminal):
   ```powershell
   & "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" compute ssh tracking --zone africa-south1-b --project gen-lang-client-0101078644 --command "sudo cat /etc/attendance/initial-admin-password"
   ```
2. Open **https://raya.34.35.174.159.nip.io**, log in as `mazenabdelrehem2013@gmail.com` with it.
3. You must choose your own password (at least 10 characters).
4. Then set up the company: **Locations & departments** (branch, working hours Mon–Sat 09:00–18:00, offices with
   their GPS position and radius, departments) → **Employees** (managers first, then staff) → **QR screens** if offices
   use them. Real phones come in Phase 19.

There are **no demo users or demo data** on the live system.

## Updating to a new version

From this PC (about 2–3 minutes; if the new version doesn't start, the previous one is restored automatically):
```powershell
powershell -ExecutionPolicy Bypass -File D:\claude\attendance-system\infrastructure\server\deploy-from-pc.ps1
```
It builds the dashboard, packs only the code, uploads it, installs packages, applies database changes and restarts.
Ends with `Healthy: {...}` and `Done: https://raya.34.35.174.159.nip.io`.

The one-time installation (already done) is the same command with `-Install`.

## What runs on the server

| Service | Does |
|---|---|
| `attendance-api` | API + dashboard (2 processes, on 127.0.0.1:8100 behind nginx, max 900 MB memory) |
| `attendance-scheduler` | every minute: closes the previous day after 00:15, scheduled reports, security alert rules; after 02:00: audit-log tamper check + data clean-up |
| nginx | HTTPS for `raya.34.35.174.159.nip.io` only; CargoTrace (`34.35.174.159.nip.io`) and rewjido (port 8080) unchanged |
| cron | nightly database backup |

Security on the server: the services run as their own user `attendance` with a read-only system
(systemd hardening). The API's database account cannot delete attendance, audit or security data. The owner
password is only given to the scheduler (for the nightly clean-up). Secrets are readable by root and the service only.

## Looking at it

```powershell
$g = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
& $g compute ssh tracking --zone africa-south1-b --project gen-lang-client-0101078644 --command "systemctl status attendance-api attendance-scheduler --no-pager | head -20"
& $g compute ssh tracking --zone africa-south1-b --project gen-lang-client-0101078644 --command "sudo journalctl -u attendance-scheduler -n 20 --no-pager -o cat"
```
Health from anywhere: https://raya.34.35.174.159.nip.io/api/v1/health → `{"status":"ok",...}`

## Backups and restore

Every night `attendance-YYYY-MM-DD.dump` (custom format; all 35 tables, checked on 5 Oct 2026). To restore one (this
**replaces** the current data, so only after a disaster):
```bash
sudo systemctl stop attendance-api attendance-scheduler
sudo cat /var/backups/attendance/attendance-2026-10-05.dump | sudo -u postgres pg_restore --clean --if-exists -d attendance
sudo systemctl start attendance-api attendance-scheduler
```
⚠ The backups are on the **same server**: they protect against mistakes, not against losing the server. See "Not
done yet".

## Not done yet (decisions for later)

| Item | Why it matters | Cost |
|---|---|---|
| Copy backups off the server (Google Cloud Storage in Johannesburg) | survive losing the VM/disk | a few cents per month |
| Google Cloud uptime check + alert to you if the site is down or a security alert fires | you'd learn about problems immediately | free (alert by e-mail to you; not sent by the app) |
| Own domain (e.g. `attendance.raya.com`) | professional address; the phone app has the address built in, so before many phones are installed is best | ~$10–15/year or free with an existing company domain |
| Web application firewall (Cloud Armor) | extra protection against attacks | needs a load balancer (~$20+/month); the app already throttles logins and locks accounts |
| Play Integrity switched on | Phase 19 (needs the app published on Google Play) | free |
