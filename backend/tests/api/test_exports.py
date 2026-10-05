"""Phase 14: Excel and PDF exports, opened and checked like a reader would."""

import io
from datetime import time, timedelta

import pytest
from openpyxl import load_workbook
from pypdf import PdfReader
from sqlalchemy import func, select

from app.models import AuditLog, ReportRun
from tests.api.attendance_helpers import approved_device, attempt, set_time  # noqa: F401
from tests.api.test_reports import week  # noqa: F401  (the hand-made week fixture)

WEEK = {"date_from": "2026-10-05", "date_to": "2026-10-11"}


def export(client, world, fmt, who="hr", **body):
    r = client.post(f"/api/v1/reports/export/{fmt}", headers=world.h(who), json=body)
    assert r.status_code == 200, r.text
    return r


def workbook(response):
    return load_workbook(io.BytesIO(response.content))


def pdf_text(response) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages)


# --- Excel ----------------------------------------------------------------------------------


def test_monthly_excel_layout(client, week):
    r = export(client, week, "excel", report="weekly", date="2026-10-07")
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert 'filename="attendance-weekly-2026-10-05-to-2026-10-11.xlsx"' in r.headers["content-disposition"]
    wb = workbook(r)
    assert wb.sheetnames == ["Summary", "Employees", "By location", "By department", "By manager"]

    summary = wb["Summary"]
    assert summary["A2"].value == "Weekly attendance report"
    assert summary["B4"].value == "05 October 2026 – 11 October 2026"

    ws = wb["Employees"]
    headers = [c.value for c in ws[1]]
    assert headers[:3] == ["Employee", "Employee ID", "Department"] and headers[-1] == "Attendance"
    assert ws["A1"].font.bold and ws["A1"].fill.fgColor.rgb.endswith("1F5FAD")
    assert ws.freeze_panes == "B2"  # header row and name column stay visible
    assert ws.auto_filter.ref.startswith("A1:")

    rows = {row[0].value: row for row in ws.iter_rows(min_row=2)}
    ann = rows["Ann"]
    col = {h: i for i, h in enumerate(headers)}
    assert ann[col["Avg check-in"]].value == time(9, 12)
    assert ann[col["Avg check-in"]].number_format == "hh:mm"
    # 985 minutes = 16h25m, stored as an Excel duration (openpyxl reads it back as a timedelta).
    assert ann[col["Total hours"]].value == timedelta(minutes=475 + 510)
    assert ann[col["Total hours"]].number_format == "[h]:mm"
    assert ann[col["Attendance"]].value == 0.75 and ann[col["Attendance"]].number_format == "0.0%"

    total = next(row for row in ws.iter_rows() if str(row[0].value).startswith("Total"))
    assert total[col["Present"]].value.startswith("=SUM(")
    assert total[col["Attendance"]].value.startswith("=IF(")


def test_daily_excel(client, week):
    wb = workbook(export(client, week, "excel", report="daily", date="2026-10-06"))
    ws = wb["Attendance"]
    headers = [c.value for c in ws[1]]
    assert headers == ["Employee", "Employee ID", "Department", "Manager", "Location", "Check-in", "Check-out",
                       "Working hours", "Status", "Verification"]
    ann = next(row for row in ws.iter_rows(min_row=2) if row[0].value == "Ann")
    assert (ann[5].value, ann[6].value, ann[8].value) == (time(9, 30), time(18, 0), "Late")


def test_excel_blocks_formula_injection(client, world, set_time):
    client.put(f"/api/v1/employees/{world.ids['ben']}", headers=world.h("hr"),
               json={"full_name": '=HYPERLINK("http://evil","click")'})
    ws = workbook(export(client, world, "excel", report="daily", date="2026-10-05"))["Attendance"]
    cell = next(row[0] for row in ws.iter_rows(min_row=2) if "HYPERLINK" in str(row[0].value))
    assert cell.data_type == "s" and cell.value.startswith("'=")


# --- PDF ------------------------------------------------------------------------------------


def test_monthly_pdf_contents(client, week):
    r = export(client, week, "pdf", report="weekly", date="2026-10-07")
    assert r.content.startswith(b"%PDF") and r.headers["content-type"] == "application/pdf"
    text = pdf_text(r)
    for expected in ("Weekly attendance report", "05 October 2026 – 11 October 2026", "Ann", "Ben",
                     "Attendance", "75.0%", "Total", "By location", "Page 1"):
        assert expected in text, expected


def test_pdf_handles_nigerian_letters_and_markup_in_names(client, world, set_time):
    client.put(f"/api/v1/employees/{world.ids['ann']}", headers=world.h("hr"), json={"full_name": "Adéṣọlá Ọ̀ṣun"})
    client.put(f"/api/v1/employees/{world.ids['ben']}", headers=world.h("hr"), json={"full_name": "Ben <b>&</b> Co"})
    text = pdf_text(export(client, world, "pdf", report="daily", date="2026-10-05"))
    assert "Adéṣọlá" in text
    assert "Ben <b>&</b> Co" in text  # shown as text, not interpreted as formatting


@pytest.mark.parametrize("report,extra", [
    ("daily", {"date": "2026-10-06"}), ("weekly", {"date": "2026-10-06"}), ("monthly", {"month": "2026-10"}),
    ("period", WEEK), ("late", WEEK), ("absence", WEEK), ("suspicious", WEEK),
])
@pytest.mark.parametrize("fmt", ["excel", "pdf"])
def test_every_report_exports_in_both_formats(client, week, report, extra, fmt):
    r = export(client, week, fmt, report=report, **extra)
    assert len(r.content) > 1000


def test_late_report_excel_has_minutes(client, week):
    ws = workbook(export(client, week, "excel", report="late", **WEEK))["Late arrivals"]
    headers = [c.value for c in ws[1]]
    row = [c.value for c in ws[2]]
    assert row[headers.index("Minutes late")] == 30 and row[headers.index("Employee")] == "Ann"


# --- Access & record keeping ----------------------------------------------------------------


def test_manager_exports_only_their_team(client, week):
    ws = workbook(export(client, week, "excel", who="mgr_b", report="weekly", date="2026-10-07"))["Employees"]
    names = [row[0].value for row in ws.iter_rows(min_row=2) if not str(row[0].value).startswith("Total")]
    assert names == ["Cal"]
    assert workbook(export(client, week, "excel", who="mgr_b", report="weekly", date="2026-10-07"))["Summary"]["B6"].value == "Your team"


def test_employees_cannot_export(client, world):
    r = client.post("/api/v1/reports/export/excel", headers=world.h("ann"), json={"report": "daily"})
    assert r.status_code == 403


def test_exports_are_recorded(client, week, test_session_factory):
    export(client, week, "pdf", report="monthly", month="2026-10", location_id=str(week.lagos_id))
    with test_session_factory() as db:
        run = db.scalar(select(ReportRun).order_by(ReportRun.created_at.desc()))
        assert run.format.value == "PDF" and run.report_type.value == "MONTHLY"
        assert run.parameters["location_id"] == str(week.lagos_id) and run.row_count == 4
        entry = db.scalar(select(AuditLog).where(AuditLog.object_id == str(run.id)))
        assert entry.action == "REPORT_EXPORTED" and entry.actor_role == "HR"
        assert db.scalar(select(func.count()).select_from(ReportRun)) >= 1


def test_invalid_export_request(client, world):
    r = client.post("/api/v1/reports/export/pdf", headers=world.h("hr"), json={"report": "yearly"})
    assert r.status_code == 422


def test_daily_status_shows_missing_checkout_and_local_generated_time(client, week):
    text = pdf_text(export(client, week, "pdf", report="daily", date="2026-10-10"))  # Saturday: never checked out
    flat = " ".join(text.split())  # table cells wrap onto several lines
    assert "Present · Missing check-out" in flat
    assert "(Africa/Lagos)" in text
