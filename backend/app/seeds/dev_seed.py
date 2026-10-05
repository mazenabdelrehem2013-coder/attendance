"""Loads demo data into the DEVELOPMENT database. Safe to run twice (does nothing the 2nd time).

    .venv\\Scripts\\python -m app.seeds.dev_seed

All demo users get the password SEED_DEFAULT_PASSWORD from backend/.env.
Office coordinates are approximate city points - replace them with the real office coordinates.
"""

import sys
from datetime import date, time
from decimal import Decimal

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import make_session_factory
from app.models import (
    AttendancePolicy,
    AuditLog,
    Branch,
    Department,
    Employee,
    EmployeeLocation,
    Holiday,
    Location,
    Manager,
    NotificationSetting,
    Organization,
    ReportSetting,
    RetentionSetting,
    User,
    WorkSchedule,
    WorkScheduleDay,
)
from app.models.enums import (
    NotificationChannel,
    NotificationEvent,
    PolicyAction,
    ReportType,
    RetentionCategory,
    Role,
    VerificationMode,
)

ORG_NAME = "Demo Company Ltd"

# code, city/office name, address, latitude, longitude
OFFICES = [
    ("LOS", "Lagos Office", "Victoria Island, Lagos", "6.428100", "3.421900"),
    ("ABV", "Abuja Office", "Central Business District, Abuja", "9.056300", "7.498500"),
    ("PHC", "Port Harcourt Office", "Old GRA, Port Harcourt", "4.815600", "7.049800"),
    ("ONI", "Onitsha Office", "Onitsha, Anambra", "6.141300", "6.802900"),
    ("ENU", "Enugu Office", "Independence Layout, Enugu", "6.458400", "7.546400"),
    ("UYO", "Uyo Office", "Uyo, Akwa Ibom", "5.037700", "7.912800"),
]

DEPARTMENTS = [
    ("HR", "Human Resources"),
    ("FIN", "Finance"),
    ("OPS", "Operations"),
    ("SAL", "Sales"),
    ("IT", "Information Technology"),
]

# Fixed-date Nigerian public holidays. Movable ones (Easter, Eid) must be added by HR each year.
HOLIDAYS = [
    (date(2026, 10, 1), "Independence Day"),
    (date(2026, 12, 25), "Christmas Day"),
    (date(2026, 12, 26), "Boxing Day"),
    (date(2027, 1, 1), "New Year's Day"),
    (date(2027, 5, 1), "Workers' Day"),
    (date(2027, 6, 12), "Democracy Day"),
    (date(2027, 10, 1), "Independence Day"),
    (date(2027, 12, 25), "Christmas Day"),
    (date(2027, 12, 26), "Boxing Day"),
]

# email, role, employee_code, full name, department, office codes (first = primary), manager key
PEOPLE = [
    ("admin@example.com", Role.ADMIN, None, "System Administrator", None, [], None),
    ("hr@example.com", Role.HR, "EMP-0001", "Ngozi Okafor", "HR", ["LOS"], None),
    ("manager.lagos@example.com", Role.MANAGER, "EMP-0002", "Tunde Bakare", "OPS", ["LOS"], None),
    ("manager.abuja@example.com", Role.MANAGER, "EMP-0003", "Aisha Bello", "OPS", ["ABV"], None),
    ("emp0101@example.com", Role.EMPLOYEE, "EMP-0101", "Chinedu Eze", "SAL", ["LOS"], "LOS"),
    ("emp0102@example.com", Role.EMPLOYEE, "EMP-0102", "Funmi Adeyemi", "FIN", ["LOS"], "LOS"),
    ("emp0103@example.com", Role.EMPLOYEE, "EMP-0103", "Emeka Nwosu", "IT", ["LOS", "ABV"], "LOS"),
    ("emp0104@example.com", Role.EMPLOYEE, "EMP-0104", "Bisi Ogunleye", "OPS", ["LOS"], "LOS"),
    ("emp0105@example.com", Role.EMPLOYEE, "EMP-0105", "Ibrahim Musa", "SAL", ["ABV"], "ABV"),
    ("emp0106@example.com", Role.EMPLOYEE, "EMP-0106", "Hauwa Sani", "FIN", ["ABV"], "ABV"),
    ("emp0107@example.com", Role.EMPLOYEE, "EMP-0107", "Grace Akpan", "OPS", ["UYO"], "LOS"),
    ("emp0108@example.com", Role.EMPLOYEE, "EMP-0108", "Obinna Okeke", "SAL", ["ONI"], "LOS"),
    ("emp0109@example.com", Role.EMPLOYEE, "EMP-0109", "Kelechi Uche", "IT", ["ENU"], "LOS"),
    ("emp0110@example.com", Role.EMPLOYEE, "EMP-0110", "Tamuno Briggs", "OPS", ["PHC"], "ABV"),
]


def seed() -> None:
    settings = get_settings()
    password = settings.seed_default_password.get_secret_value()
    if len(password) < 10:
        sys.exit("SEED_DEFAULT_PASSWORD in backend/.env must be at least 10 characters.")

    Session = make_session_factory()  # app role, exactly like the API will connect
    with Session.begin() as db:
        if db.scalar(select(Organization).where(Organization.name == ORG_NAME)):
            print(f"'{ORG_NAME}' already exists - nothing to do.")
            return

        org = Organization(
            name=ORG_NAME,
            default_timezone="Africa/Lagos",
            settings={"report_company_name": ORG_NAME, "email_from_name": "Attendance System"},
        )
        db.add(org)
        db.flush()

        schedule = WorkSchedule(
            organization_id=org.id,
            name="Standard 09:00-18:00 Mon-Sat",
            grace_minutes=15,
            early_departure_minutes=0,
            days=[
                WorkScheduleDay(weekday=d, start_time=time(9, 0), end_time=time(18, 0))
                for d in range(6)  # 0 = Monday ... 5 = Saturday
            ],
        )
        db.add(schedule)
        db.flush()

        locations: dict[str, Location] = {}
        for code, name, address, lat, lng in OFFICES:
            branch = Branch(organization_id=org.id, name=name.replace(" Office", " Branch"), code=code)
            db.add(branch)
            db.flush()
            loc = Location(
                organization_id=org.id,
                branch_id=branch.id,
                name=name,
                code=code,
                address=address,
                latitude=Decimal(lat),
                longitude=Decimal(lng),
                radius_m=200,
                timezone="Africa/Lagos",
                work_schedule_id=schedule.id,
            )
            db.add(loc)
            locations[code] = loc
        db.flush()

        departments: dict[str, Department] = {}
        for code, name in DEPARTMENTS:
            dept = Department(organization_id=org.id, name=name, code=code)
            db.add(dept)
            departments[code] = dept
        db.flush()

        # People: users first, then employees, then manager links.
        managers: dict[str, Manager] = {}
        employees: list[tuple[Employee, list[str], str | None]] = []
        admin_user = None
        for email, role, emp_code, full_name, dept_code, office_codes, manager_key in PEOPLE:
            user = User(
                organization_id=org.id,
                email=email,
                password_hash=hash_password(password),
                role=role,
                must_change_password=False,  # demo convenience; real accounts default to True
            )
            db.add(user)
            db.flush()
            if role == Role.ADMIN:
                admin_user = user
            if emp_code is None:
                continue
            emp = Employee(
                organization_id=org.id,
                user_id=user.id,
                employee_code=emp_code,
                full_name=full_name,
                department_id=departments[dept_code].id,
                hire_date=date(2025, 1, 6),
            )
            db.add(emp)
            db.flush()
            employees.append((emp, office_codes, manager_key))
            if role == Role.MANAGER:
                mgr = Manager(user_id=user.id, employee_id=emp.id)
                db.add(mgr)
                db.flush()
                managers[office_codes[0]] = mgr

        for emp, office_codes, manager_key in employees:
            if manager_key:
                emp.manager_id = managers[manager_key].id
            for i, code in enumerate(office_codes):
                db.add(
                    EmployeeLocation(
                        employee_id=emp.id,
                        location_id=locations[code].id,
                        is_primary=(i == 0),
                        valid_from=date(2025, 1, 6),
                        created_by=admin_user.id,
                    )
                )

        for day, name in HOLIDAYS:
            db.add(Holiday(organization_id=org.id, holiday_date=day, name=name))

        # Decision 11.6: every failed check is FLAGGED; flagged events don't count until HR approves.
        db.add(
            AttendancePolicy(
                organization_id=org.id,
                verification_mode=VerificationMode.GPS_ONLY,  # switch to GPS_QR once screens are installed
                on_mock_location=PolicyAction.FLAG,
                on_integrity_fail=PolicyAction.FLAG,
                on_poor_accuracy=PolicyAction.FLAG,
                on_stale_location=PolicyAction.FLAG,
                on_outside_geofence=PolicyAction.FLAG,
                on_impossible_travel=PolicyAction.FLAG,
                on_clock_skew=PolicyAction.FLAG,
                on_qr_fail=PolicyAction.FLAG,
                flagged_counts_before_review=False,
            )
        )

        for event in NotificationEvent:
            roles = ["HR"]
            if event in (NotificationEvent.LATE_EMPLOYEE, NotificationEvent.MISSING_CHECKOUT):
                roles = ["HR", "MANAGER"]
            db.add(
                NotificationSetting(
                    organization_id=org.id,
                    event_type=event,
                    channel=NotificationChannel.IN_APP,
                    recipient_roles=roles,
                    thresholds={"absences_in_30_days": 3}
                    if event == NotificationEvent.HIGH_ABSENCE
                    else {},
                )
            )

        db.add_all(
            [
                ReportSetting(
                    organization_id=org.id,
                    name="Daily attendance (09:30, Mon-Sat)",
                    report_type=ReportType.DAILY,
                    cron_expression="30 9 * * 1-6",
                    formats=["EXCEL", "PDF"],
                    recipient_roles=["HR", "MANAGER"],
                    created_by=admin_user.id,
                ),
                ReportSetting(
                    organization_id=org.id,
                    name="Weekly management summary (Monday 08:00)",
                    report_type=ReportType.WEEKLY,
                    cron_expression="0 8 * * 1",
                    formats=["PDF"],
                    recipient_roles=["HR", "ADMIN"],
                    created_by=admin_user.id,
                ),
                ReportSetting(
                    organization_id=org.id,
                    name="Monthly attendance (1st of month 08:00)",
                    report_type=ReportType.MONTHLY,
                    cron_expression="0 8 1 * *",
                    formats=["EXCEL", "PDF"],
                    recipient_roles=["HR"],
                    created_by=admin_user.id,
                ),
            ]
        )

        retention_days = {
            RetentionCategory.ATTENDANCE: 2555,  # ~7 years
            RetentionCategory.AUDIT_LOGS: 2555,
            RetentionCategory.SECURITY_EVENTS: 730,
            RetentionCategory.RAW_LOCATION: 365,
            RetentionCategory.REPORT_FILES: 90,
            RetentionCategory.NOTIFICATIONS: 180,
        }
        for category, days in retention_days.items():
            db.add(RetentionSetting(organization_id=org.id, data_category=category, retain_days=days))

        db.add(
            AuditLog(
                organization_id=org.id,
                actor_user_id=None,
                actor_role="SYSTEM",
                action="DEMO_DATA_SEEDED",
                object_type="organization",
                object_id=str(org.id),
                new_value={"locations": len(OFFICES), "people": len(PEOPLE)},
            )
        )

    print(
        f"Seeded '{ORG_NAME}': {len(OFFICES)} locations, {len(DEPARTMENTS)} departments, "
        f"{len(PEOPLE)} users ({len(employees)} employees), {len(HOLIDAYS)} holidays."
    )
    print("Demo logins: admin@example.com, hr@example.com, manager.lagos@example.com, "
          "emp0101@example.com ... - password = SEED_DEFAULT_PASSWORD in backend/.env")


if __name__ == "__main__":
    seed()
