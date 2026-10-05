"""One printable layout per report, shared by the Excel and PDF writers so both always show
exactly the same columns, values, totals and summary."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from app.schemas.reports import DailyReport, ListReport, PeriodReport

Kind = Literal["text", "date", "time", "minutes", "int", "percent"]

STATUS = {
    "PRESENT": "Present", "LATE": "Late", "ABSENT": "Absent", "PENDING_REVIEW": "Pending review",
    "NOT_CHECKED_IN": "Not checked in", "ON_LEAVE": "On leave", "HOLIDAY": "Holiday",
    "NON_WORKING_DAY": "Day off", "VERIFIED": "Verified", "MISSING_CHECKOUT": "Missing check-out",
    "EARLY_DEPARTURE": "Left early",
}


@dataclass
class Column:
    header: str
    key: str
    kind: Kind = "text"
    total: bool = False  # sum this column in the totals row
    width: int = 14  # Excel character width; PDF uses it as a proportion
    short: str | None = None  # shorter title for narrow PDF columns


@dataclass
class Table:
    title: str
    columns: list[Column]
    rows: list[dict[str, Any]]
    totals: bool = True
    # Attendance % in the totals row = sum(present) / sum(working)
    rate_from: tuple[str, str] | None = None


@dataclass
class ReportDocument:
    company: str
    title: str
    period: str
    generated_at: datetime
    scope: str
    summary: list[tuple[str, Any, Kind]]
    main: Table
    extra: list[Table] = field(default_factory=list)
    file_stem: str = "report"
    timezone: str = "Africa/Lagos"

    @property
    def generated_label(self) -> str:
        local = self.generated_at.astimezone(ZoneInfo(self.timezone))
        return f"{local.strftime('%d %b %Y %H:%M')} ({self.timezone})"


def _fmt_period(start: date, end: date) -> str:
    if start == end:
        return start.strftime("%A %d %B %Y")
    return f"{start.strftime('%d %B %Y')} – {end.strftime('%d %B %Y')}"


def _pretty(value: str | None) -> str:
    return STATUS.get(value or "", (value or "").replace("_", " ").capitalize())


def from_daily(r: DailyReport, company: str, scope: str) -> ReportDocument:
    cols = [
        Column("Employee", "employee", width=24), Column("Employee ID", "employee_code", width=13),
        Column("Department", "department", width=18), Column("Manager", "manager", width=18),
        Column("Location", "location", width=16), Column("Check-in", "check_in", "time", width=10),
        Column("Check-out", "check_out", "time", width=10),
        Column("Working hours", "worked_minutes", "minutes", total=True, width=12),
        Column("Status", "status", width=16), Column("Verification", "verification_status", width=15),
    ]
    def status(row) -> str:
        text = _pretty(row.status)
        if row.departure_status in ("MISSING_CHECKOUT", "EARLY_DEPARTURE"):
            text += " · " + _pretty(row.departure_status)
        return text

    rows = [{**row.model_dump(), "status": status(row), "verification_status": _pretty(row.verification_status)}
            for row in r.rows]
    t = r.totals
    summary = [("Employees", t["employees"], "int"), ("Present", t["present"], "int"), ("Late", t["late"], "int"),
               ("Absent", t["absent"], "int"), ("Missing check-out", t["missing_checkout"], "int"),
               ("Pending HR review", t["pending_review"], "int"), ("On leave", t["on_leave"], "int")]
    return ReportDocument(company, r.title, _fmt_period(r.date, r.date), r.generated_at, scope, summary,
                          Table("Attendance", cols, rows), file_stem=f"attendance-daily-{r.date.isoformat()}")


PERIOD_COLUMNS = [
    Column("Employee", "employee", width=22), Column("Employee ID", "employee_code", width=14, short="ID"),
    Column("Department", "department", width=16, short="Dept."), Column("Manager", "manager", width=16),
    Column("Location", "location", width=15),
    Column("Working days", "working_days", "int", True, 9, "Work days"),
    Column("Present", "present_days", "int", True, 9, "Pres."),
    Column("Absent", "absent_days", "int", True, 9, "Abs."), Column("Late", "late_days", "int", True, 8),
    Column("Left early", "early_departure_days", "int", True, 9, "Early"),
    Column("Missing check-out", "missing_checkout_days", "int", True, 10, "No out"),
    Column("Leave", "leave_days", "int", True, 8),
    Column("Avg check-in", "average_check_in", "time", width=10, short="Avg in"),
    Column("Avg check-out", "average_check_out", "time", width=10, short="Avg out"),
    Column("Avg hours", "average_worked_minutes", "minutes", width=10, short="Avg hrs"),
    Column("Total hours", "total_worked_minutes", "minutes", True, 11, "Total hrs"),
    Column("Attendance", "attendance_rate", "percent", width=11, short="Attend."),
]

GROUP_COLUMNS = [
    Column("Name", "name", width=24), Column("Employees", "employees", "int", True, 10),
    Column("Working days", "working_days", "int", True, 12), Column("Present days", "present_days", "int", True, 12),
    Column("Late days", "late_days", "int", True, 10), Column("Absent days", "absent_days", "int", True, 11),
    Column("Attendance", "attendance_rate", "percent", width=11),
]


def from_period(r: PeriodReport, company: str, scope: str, kind: str) -> ReportDocument:
    t = r.totals
    summary = [("Employees", t["employees"], "int"), ("Working days", t["working_days"], "int"),
               ("Present days", t["present_days"], "int"), ("Absent days", t["absent_days"], "int"),
               ("Late days", t["late_days"], "int"), ("Left early", t["early_departure_days"], "int"),
               ("Missing check-out", t["missing_checkout_days"], "int"),
               ("Hours worked", t["total_worked_minutes"], "minutes"),
               ("Attendance", t["attendance_rate"], "percent")]
    rate = ("present_days", "working_days")
    extra = [Table(f"By {name}", GROUP_COLUMNS, [g.model_dump() for g in groups], rate_from=rate)
             for name, groups in (("location", r.by_location), ("department", r.by_department),
                                  ("manager", r.by_manager))]
    return ReportDocument(company, r.title, _fmt_period(r.date_from, r.date_to), r.generated_at, scope, summary,
                          Table("Employees", PERIOD_COLUMNS, [row.model_dump() for row in r.rows], rate_from=rate),
                          extra, file_stem=f"attendance-{kind}-{r.date_from.isoformat()}-to-{r.date_to.isoformat()}")


def from_list(r: ListReport, company: str, scope: str, kind: str) -> ReportDocument:
    cols = [Column("Date", "date", "date", width=12), Column("Employee", "employee", width=24),
            Column("Employee ID", "employee_code", width=12), Column("Department", "department", width=18),
            Column("Location", "location", width=16), Column("Details", "detail", width=60)]
    if kind == "late":
        cols.insert(5, Column("Minutes late", "minutes", "int", True, 10))
    return ReportDocument(company, r.title, _fmt_period(r.date_from, r.date_to), r.generated_at, scope,
                          [("Entries", len(r.rows), "int")], Table(r.title, cols, [x.model_dump() for x in r.rows]),
                          file_stem=f"attendance-{kind}-{r.date_from.isoformat()}-to-{r.date_to.isoformat()}")
