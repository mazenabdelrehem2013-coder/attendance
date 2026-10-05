r"""Phone simulator for LOCAL DEVELOPMENT ONLY - behaves like the real app will (Phase 10):
registers the phone with its own key, gets a challenge, signs the request and checks in/out.

Uses the demo password (SEED_DEFAULT_PASSWORD from backend/.env) and approves new phones as
hr@example.com automatically. Keys are kept in backend/.dev_phones/ (never committed).

Examples (PowerShell, in the backend folder, with the API running):
    .venv\Scripts\python scripts\simulate_phone.py EMP-0101 check-in
    .venv\Scripts\python scripts\simulate_phone.py EMP-0101 check-out
    .venv\Scripts\python scripts\simulate_phone.py EMP-0101 check-in --meters-north 850
    .venv\Scripts\python scripts\simulate_phone.py EMP-0101 check-in --accuracy 150
    .venv\Scripts\python scripts\simulate_phone.py EMP-0101 check-in --mock
    .venv\Scripts\python scripts\simulate_phone.py EMP-0101 check-in --old-reading
    .venv\Scripts\python scripts\simulate_phone.py EMP-0101 check-in --qr "Q1.xxxx..."
    .venv\Scripts\python scripts\simulate_phone.py EMP-0101 today
"""

import argparse
import base64
import hashlib
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings  # noqa: E402
from app.models.enums import AttendanceAction  # noqa: E402
from app.schemas.attendance import AttendanceSubmission  # noqa: E402
from app.services.attendance.canonical import canonical_payload  # noqa: E402

API = "http://localhost:8000/api/v1"
KEY_DIR = Path(__file__).resolve().parents[1] / ".dev_phones"


def login(client: httpx.Client, who: str, password: str) -> dict:
    r = client.post(f"{API}/auth/login", json={"identifier": who, "password": password})
    if r.status_code != 200:
        sys.exit(f"Login failed for {who}: {r.text}")
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def phone_key(employee: str) -> ec.EllipticCurvePrivateKey:
    KEY_DIR.mkdir(exist_ok=True)
    path = KEY_DIR / f"{employee.upper()}.pem"
    if path.exists():
        return serialization.load_pem_private_key(path.read_bytes(), None)
    key = ec.generate_private_key(ec.SECP256R1())
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    return key


def ensure_phone(client, emp_headers, employee, password) -> str:
    key = phone_key(employee)
    public = base64.b64encode(key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).decode()
    device = client.post(f"{API}/devices/register", headers=emp_headers, json={
        "device_fingerprint": hashlib.sha256(f"simulated-phone-{employee.upper()}".encode()).hexdigest(),
        "install_id": f"sim-{employee.lower()}", "device_model": "Simulated phone",
        "os_version": "Android 15", "app_version": "simulator", "public_key": public,
    })
    if device.status_code != 200:
        sys.exit(f"Phone registration failed: {device.text}")
    device = device.json()
    if device["status"] == "PENDING_APPROVAL":
        hr = login(client, "hr@example.com", password)
        client.post(f"{API}/devices/{device['id']}/approve", headers=hr, json={"note": "simulator"})
        print("  (new simulated phone approved by hr@example.com)")
    return device["id"]


def main() -> None:
    p = argparse.ArgumentParser(description="Simulated phone for local testing")
    p.add_argument("employee", help="Employee ID or email, e.g. EMP-0101")
    p.add_argument("action", choices=["check-in", "check-out", "today"])
    p.add_argument("--lat", type=float, default=6.428300, help="default: Lagos office")
    p.add_argument("--lng", type=float, default=3.422000)
    p.add_argument("--meters-north", type=float, default=0, help="move the position north by N meters")
    p.add_argument("--accuracy", type=float, default=10)
    p.add_argument("--mock", action="store_true", help="report a mock (fake) location")
    p.add_argument("--old-reading", action="store_true", help="send a 2-minute-old GPS reading")
    p.add_argument("--qr", help="token from GET /qr/current")
    args = p.parse_args()

    password = get_settings().seed_default_password.get_secret_value()
    with httpx.Client(timeout=20) as client:
        emp = login(client, args.employee, password)
        if args.action == "today":
            t = client.get(f"{API}/attendance/today", headers=emp).json()
            print(f"{t['date']}  {t['day_type']}  state={t['state']}  next={t['next_action']}")
            for a in t["attempts"]:
                print(f"  {a['server_time'][11:19]}  {a['event_type']:9}  {a['result']:8}  {a['message']}")
            return

        device_id = ensure_phone(client, emp, args.employee, password)
        action = AttendanceAction.CHECK_IN if args.action == "check-in" else AttendanceAction.CHECK_OUT
        ch = client.post(f"{API}/attendance/challenge", headers=emp,
                         json={"action": action.value, "device_id": device_id})
        if ch.status_code != 200:
            sys.exit(f"Challenge refused: {ch.text}")
        ch = ch.json()

        body = {
            "client_request_id": str(uuid.uuid4()), "challenge_id": ch["challenge_id"],
            "nonce": ch["nonce"], "device_id": device_id,
            "latitude": round(args.lat + args.meters_north / 111_195, 6), "longitude": args.lng,
            "accuracy_m": args.accuracy, "fix_age_ms": 120_000 if args.old_reading else 1500,
            "is_mock_location": args.mock, "device_time": datetime.now(UTC).isoformat(),
            "app_version": "simulator", "qr_token": args.qr,
        }
        payload = canonical_payload(action, AttendanceSubmission(**body, signature="pending"))
        body["signature"] = base64.b64encode(
            phone_key(args.employee).sign(payload.encode(), ec.ECDSA(hashes.SHA256()))).decode()

        r = client.post(f"{API}/attendance/{args.action}", headers=emp, json=body)
        if r.status_code != 200:
            sys.exit(f"Error {r.status_code}: {r.text}")
        res = r.json()
        print(f"{res['result']:8}  status={res['status']}  location={res['location']}  "
              f"distance={res['distance_meters']} m")
        print(f"  Employee sees: {res['message']}")


if __name__ == "__main__":
    main()
