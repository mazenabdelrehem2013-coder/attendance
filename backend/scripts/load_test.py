r"""Load test of the morning rush: many employees checking in within a few minutes.

Uses the TEST database only (never attendance_dev). It
  1. creates a separate "Load Test" company with N employees, each with an approved phone and
     its own EC P-256 key (like the Android Keystore), and gives each a login token,
  2. starts its own copy of the API on port 8001 (unless --url is given),
  3. lets every simulated phone do exactly what the real app does at the office door:
        POST /attendance/challenge -> sign the canonical payload -> POST /attendance/check-in
        -> GET /attendance/today
     with arrivals spread over --window seconds and at most --concurrency requests at once,
  4. prints response times per step and the error count. Exit code 1 if any check failed or the
     95th percentile is above --max-p95-ms.

Run (from the backend folder):
    .venv\Scripts\python scripts\load_test.py                      (500 employees in 120 s)
    .venv\Scripts\python scripts\load_test.py --employees 1000 --window 60 --workers 4
    .venv\Scripts\python scripts\load_test.py --double-tap     (each phone sends 2 check-ins at
                                                               the same instant: exactly 1 may count)
"""

import argparse
import base64
import os
import random
import statistics
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, time as dtime
from decimal import Decimal
from pathlib import Path

os.environ["APP_ENV"] = "test"  # before importing the app: everything below uses the TEST database
os.environ["RUN_SCHEDULER_IN_API"] = "false"
BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import httpx  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.session import make_session_factory  # noqa: E402
from app.models import (  # noqa: E402
    Branch,
    DeviceRegistration,
    Employee,
    EmployeeLocation,
    Location,
    Organization,
    User,
    WorkSchedule,
    WorkScheduleDay,
)
from app.models.enums import AttendanceAction, DeviceStatus, Role  # noqa: E402
from app.schemas.attendance import AttendanceSubmission  # noqa: E402
from app.services.attendance.canonical import canonical_payload  # noqa: E402

OFFICE = (Decimal("6.4281"), Decimal("3.4219"))


class Phone:
    def __init__(self, employee_id, device_id, key, token):
        self.employee_id, self.device_id, self.key, self.token = employee_id, device_id, key, token


def migrate_test_db() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.cmd_opts = type("opts", (), {"x": ["db=test"]})()
    command.upgrade(cfg, "head")


def create_company(n: int) -> list[Phone]:
    """N employees with approved phones in a new company (test database)."""
    tag = uuid.uuid4().hex[:6]
    password_hash = hash_password(uuid.uuid4().hex)  # nobody logs in with it; tokens are issued below
    phones: list[Phone] = []
    started = time.perf_counter()
    with make_session_factory(test=True).begin() as db:
        org = Organization(name=f"Load Test {tag}")
        db.add(org)
        db.flush()
        branch = Branch(organization_id=org.id, name="Main", code="MAIN")
        schedule = WorkSchedule(organization_id=org.id, name="Std",
                                days=[WorkScheduleDay(weekday=d, start_time=dtime(9), end_time=dtime(18)) for d in range(7)])
        db.add_all([branch, schedule])
        db.flush()
        office = Location(organization_id=org.id, branch_id=branch.id, name="Lagos", code="LOS", latitude=OFFICE[0],
                          longitude=OFFICE[1], radius_m=200, work_schedule_id=schedule.id)
        db.add(office)
        db.flush()
        for i in range(n):
            user = User(organization_id=org.id, email=f"load{i}-{tag}@example.com", password_hash=password_hash,
                        role=Role.EMPLOYEE, must_change_password=False)
            db.add(user)
            db.flush()
            emp = Employee(organization_id=org.id, user_id=user.id, employee_code=f"L{tag}-{i:05d}".upper(),
                           full_name=f"Load Employee {i}")
            db.add(emp)
            db.flush()
            db.add(EmployeeLocation(employee_id=emp.id, location_id=office.id, is_primary=True))
            key = ec.generate_private_key(ec.SECP256R1())
            public = base64.b64encode(key.public_key().public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)).decode()
            device = DeviceRegistration(employee_id=emp.id, device_fingerprint=uuid.uuid4().hex + uuid.uuid4().hex,
                                        install_id=uuid.uuid4().hex, device_model="Load phone", os_version="Android 15",
                                        app_version="1.0.0", public_key=public, key_algorithm="EC_P256",
                                        status=DeviceStatus.ACTIVE, approved_at=datetime.now(UTC))
            db.add(device)
            db.flush()
            token, _ = create_access_token(user_id=user.id, organization_id=org.id, role="EMPLOYEE",
                                           token_version=user.token_version)
            phones.append(Phone(emp.id, device.id, key, token))
    print(f"Created company 'Load Test {tag}' with {n} employees and approved phones "
          f"in {time.perf_counter() - started:.1f} s")
    return phones


class Stats:
    def __init__(self):
        self.lock = threading.Lock()
        self.times: dict[str, list[float]] = {}
        self.errors: list[str] = []
        self.results: dict[str, int] = {}

    def add(self, step: str, ms: float):
        with self.lock:
            self.times.setdefault(step, []).append(ms)

    def error(self, text: str):
        with self.lock:
            self.errors.append(text)

    def result(self, value: str):
        with self.lock:
            self.results[value] = self.results.get(value, 0) + 1


def timed(stats: Stats, step: str, call):
    started = time.perf_counter()
    response = call()
    stats.add(step, (time.perf_counter() - started) * 1000)
    if response.status_code != 200:
        raise RuntimeError(f"{step}: HTTP {response.status_code} {response.text[:200]}")
    return response.json()


def _signed_body(client: httpx.Client, phone: Phone, stats: Stats, headers: dict) -> dict:
    challenge = timed(stats, "1 challenge", lambda: client.post(
        "/attendance/challenge", headers=headers, json={"action": "CHECK_IN", "device_id": str(phone.device_id)}))
    lat = float(OFFICE[0]) + random.uniform(-0.0005, 0.0005)
    lng = float(OFFICE[1]) + random.uniform(-0.0005, 0.0005)
    body = {
        "client_request_id": str(uuid.uuid4()), "challenge_id": challenge["challenge_id"],
        "nonce": challenge["nonce"], "device_id": str(phone.device_id), "latitude": round(lat, 6),
        "longitude": round(lng, 6), "accuracy_m": round(random.uniform(5, 30), 2),
        "fix_age_ms": random.randint(500, 5000), "device_time": datetime.now(UTC).isoformat(),
        "app_version": "1.0.0", "os_version": "Android 15",
    }
    payload = canonical_payload(AttendanceAction.CHECK_IN, AttendanceSubmission(**body, signature="x"))
    body["signature"] = base64.b64encode(phone.key.sign(payload.encode(), ec.ECDSA(hashes.SHA256()))).decode()
    return body


def double_tap(client: httpx.Client, phone: Phone, stats: Stats) -> None:
    """Two check-ins from the same phone at the same instant: exactly one may be accepted."""
    headers = {"Authorization": f"Bearer {phone.token}"}
    try:
        bodies = [_signed_body(client, phone, stats, headers) for _ in range(2)]
        barrier, results = threading.Barrier(2), []

        def send(body):
            barrier.wait()
            results.append(timed(stats, "2 check-in", lambda: client.post(
                "/attendance/check-in", headers=headers, json=body))["result"])

        threads = [threading.Thread(target=send, args=(b,)) for b in bodies]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        for r in results:
            stats.result(r)
        if results.count("ACCEPTED") != 1:
            stats.error(f"double tap gave {results} (exactly one ACCEPTED expected)")
    except Exception as e:  # noqa: BLE001
        stats.error(str(e))


def check_in(client: httpx.Client, phone: Phone, stats: Stats) -> None:
    headers = {"Authorization": f"Bearer {phone.token}"}
    try:
        body = _signed_body(client, phone, stats, headers)
        result = timed(stats, "2 check-in", lambda: client.post("/attendance/check-in", headers=headers, json=body))
        stats.result(result["result"])
        if result["result"] != "ACCEPTED":
            stats.error(f"check-in {result['result']}: {result.get('message')}")
        timed(stats, "3 today (app refresh)", lambda: client.get("/attendance/today", headers=headers))
    except Exception as e:  # noqa: BLE001 - every failure is counted and reported
        stats.error(str(e))


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(p / 100 * (len(ordered) - 1))))]


def start_server(port: int, workers: int) -> subprocess.Popen:
    env = {**os.environ, "APP_ENV": "test", "RUN_SCHEDULER_IN_API": "false", "LOG_LEVEL": "WARNING"}
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--workers", str(workers),
         "--log-level", "warning"], cwd=BACKEND, env=env)
    for _ in range(60):
        try:
            if httpx.get(f"http://127.0.0.1:{port}/api/v1/health", timeout=1).status_code == 200:
                return process
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    process.terminate()
    raise SystemExit("The API did not start.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Morning-rush load test (test database only)")
    parser.add_argument("--employees", type=int, default=500)
    parser.add_argument("--window", type=float, default=120, help="seconds over which people arrive")
    parser.add_argument("--concurrency", type=int, default=50, help="max simultaneous phones")
    parser.add_argument("--workers", type=int, default=2, help="API worker processes (own server only)")
    parser.add_argument("--url", help="use an already running API instead, e.g. http://127.0.0.1:8001/api/v1")
    parser.add_argument("--max-p95-ms", type=float, default=1000)
    parser.add_argument("--double-tap", action="store_true", help="2 simultaneous check-ins per phone")
    args = parser.parse_args()

    migrate_test_db()
    phones = create_company(args.employees)
    server = None if args.url else start_server(8001, args.workers)
    base = args.url or "http://127.0.0.1:8001/api/v1"
    stats = Stats()
    try:
        limits = httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=args.concurrency)
        with httpx.Client(base_url=base, timeout=30, limits=limits) as client, \
                ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            arrivals = sorted(random.uniform(0, args.window) for _ in phones)
            print(f"{len(phones)} employees arriving over {args.window:.0f} s "
                  f"(up to {args.concurrency} at the same moment)...")
            started = time.perf_counter()
            for phone, at in zip(phones, arrivals):
                delay = at - (time.perf_counter() - started)
                if delay > 0:
                    time.sleep(delay)
                pool.submit(double_tap if args.double_tap else check_in, client, phone, stats)
            pool.shutdown(wait=True)
            elapsed = time.perf_counter() - started
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=20)

    print(f"\nFinished in {elapsed:.1f} s. Check-in results: {stats.results}")
    print(f"{'step':<24}{'requests':>9}{'median':>9}{'p95':>9}{'p99':>9}{'max':>9}   (milliseconds)")
    worst_p95 = 0.0
    for step, values in sorted(stats.times.items()):
        p95 = percentile(values, 95)
        worst_p95 = max(worst_p95, p95)
        print(f"{step:<24}{len(values):>9}{statistics.median(values):>9.0f}{p95:>9.0f}"
              f"{percentile(values, 99):>9.0f}{max(values):>9.0f}")
    total = sum(len(v) for v in stats.times.values())
    print(f"\nThroughput: {total / elapsed:.1f} requests/second. Errors: {len(stats.errors)}")
    for e in stats.errors[:10]:
        print("  -", e)
    ok = not stats.errors and worst_p95 <= args.max_p95_ms
    print("RESULT:", "PASS" if ok else f"FAIL (errors or p95 above {args.max_p95_ms:.0f} ms)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
