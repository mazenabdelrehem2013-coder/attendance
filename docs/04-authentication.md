# Phase 4 — Authentication & Roles

## What was built

| Endpoint | What it does |
|---|---|
| `POST /api/v1/auth/login` | Log in with **email or employee ID** + password. Returns an access token (15 min) and a refresh token. |
| `POST /api/v1/auth/refresh` | Swap the refresh token for new tokens. The old refresh token stops working. |
| `POST /api/v1/auth/logout` | End this device's session. |
| `GET /api/v1/auth/me` | Who is logged in (role, employee ID, name). |
| `POST /api/v1/auth/change-password` | Change your own password. Logs out every **other** device; returns fresh tokens for this one. |

### Security rules

| Rule | Detail (all values configurable in `backend/.env`) |
|---|---|
| Passwords | Stored only as Argon2id hashes. New passwords need 10+ characters, must not contain the email name or employee ID, and simple ones are rejected. |
| Access token | JWT, 15 minutes, signed with `JWT_SECRET`. Contains user, role and a **token version**. Changed role, deactivated account, suspended/terminated employee or password change → token refused immediately. |
| Refresh token | Random, stored only as a SHA-256 hash. **Rotates on every use.** Reusing an already-used token = probable theft → the whole session chain is revoked and a `REFRESH_TOKEN_REUSE` security event (HIGH) is logged. Two requests at the same moment within 20 s are tolerated. |
| Mobile vs web | Mobile: refresh token in the response (stored in the phone's secure storage, Phase 9). Web dashboard: refresh token in an `HttpOnly; SameSite=Strict` cookie that JavaScript can't read. |
| Account lockout | 5 wrong passwords → locked for 15 minutes (even the right password is refused meanwhile). Every failure is a `LOGIN_FAILED` security event. |
| IP throttling | 20 failed logins from one IP address in 15 minutes → that IP gets "too many attempts" (Cloud Armor adds a second layer in production). |
| Same answer for wrong password and unknown user | So nobody can test which emails/employee IDs exist (response time is equalised too). |
| Forced password change | Users with `must_change_password` (new accounts, HR resets — Phase 5) can only call `/auth/me` and `/auth/change-password` until they change it. |
| Roles | `require_roles(Role.HR)` etc. on every protected endpoint; **ADMIN is always allowed**. Manager "only my team" filtering comes with the data endpoints in Phase 5. |

Database change: migration **0003** adds `users.token_version` and allows security events without an organization (failed logins for unknown names).

## Try it

1. Open PowerShell and update the database (adds migration 0003):

   ```powershell
   cd D:\claude\attendance-system\backend
   .\.venv\Scripts\python -m pip install -r requirements-dev.txt
   .\.venv\Scripts\alembic upgrade head
   ```

   (Already done on your PC during development — it will just print nothing new.)

2. Start the API:

   ```powershell
   .\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
   ```

3. Open http://localhost:8000/docs
   1. Click **POST /api/v1/auth/login** → **Try it out**.
   2. Replace the example with (use the `SEED_DEFAULT_PASSWORD` value from `backend\.env`):

      ```json
      {"identifier": "EMP-0101", "password": "PASTE-SEED-PASSWORD-HERE", "client_type": "MOBILE"}
      ```

   3. **Execute** → you get `200` with `access_token` and `"full_name": "Chinedu Eze"`.
   4. Copy the `access_token` value (without quotes), click the green **Authorize** button at the top, paste it, **Authorize**, **Close**.
   5. Open **GET /api/v1/auth/me** → **Try it out** → **Execute** → your user details.
   6. Try a wrong password 5 times on `hr@example.com` → the 6th attempt says the account is locked for 15 minutes.

4. Run the tests (second PowerShell window):

   ```powershell
   cd D:\claude\attendance-system\backend
   .\.venv\Scripts\python -m pytest
   ```

   Expected: `61 passed`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `JWT_SECRET is missing or shorter than 32 characters` | `backend\.env` lacks `JWT_SECRET`. It was generated for you; if the file was replaced, add a line `JWT_SECRET=` followed by 40+ random characters. |
| Login always `401` with the demo password | Check you copied `SEED_DEFAULT_PASSWORD` exactly (no spaces/quotes). If you locked the account testing, wait 15 minutes. |
| `column users.token_version does not exist` | You skipped `alembic upgrade head` (step 1). |
| `423 ACCOUNT_LOCKED` | Expected after 5 wrong passwords; wait 15 minutes. |
