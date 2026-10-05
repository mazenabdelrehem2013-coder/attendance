# Phase 14 — Excel & PDF Exports

Every report from Phase 13 can be downloaded: **Reports** page → choose the report and filters → **Download Excel** or **Download PDF**. Managers get only their own team. Every download is recorded (report history + audit log: who, which report, filters, number of rows).

Examples are in `docs/samples/` (made from your development data).

## Excel (.xlsx)

| Sheet | Contents |
|---|---|
| **Summary** | Company name, report title, period, when it was generated (company time), who it covers, the summary numbers |
| **Employees / Attendance / list** | Blue bold headers, **filter buttons** on every column, **header row and name column frozen**, real **dates** and **times** (09:12 is a time Excel can calculate with), hours as `h:mm`, attendance as `%`, and a **totals row with live formulas** (`=SUM(...)`, attendance % = present ÷ working days) |
| **By location / By department / By manager** | (period reports) totals per group |

Prints landscape, one page wide, header repeated on every page. Text that starts with `=`, `+`, `-` or `@` is stored as plain text, so a name can never run as an Excel formula.

Downloads available: Daily, Weekly, **Monthly**, Custom period (= **employee / location / department / manager** report via the filters), **Late arrivals**, **Absences**, **Suspicious attendance**.

## PDF

A4 landscape: **company name**, **report title**, **period**, **generated date** (company time), **summary** boxes, the **detailed table** (header repeated on each page, totals row), group tables, and a footer with page numbers. Names with Nigerian letters (ẹ, ọ, ṣ, ń …) print correctly (DejaVu font on the server, Arial on Windows); characters like `<` or `&` in names are printed as text.

Daily rows show combined status, e.g. **"Late · Missing check-out"** or **"Present · Left early"**.

## API

`POST /api/v1/reports/export/excel` and `/pdf` with a JSON body:

```json
{"report": "monthly", "month": "2026-10", "location_id": "...optional..."}
```

`report` = `daily` (+`date`), `weekly` (+`date`), `monthly` (+`month`), `period` / `late` / `absence` / `suspicious` (+`date_from`, `date_to`), plus optional `department_id`, `location_id`, `manager_id`, `employee_id`.

## Try it

```powershell
cd D:\claude\attendance-system\backend
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

```powershell
cd D:\claude\attendance-system\dashboard
npm.cmd run dev
```

http://localhost:5173 → log in as `hr@example.com` → **Reports** → *Monthly report* → **Download Excel** and **Download PDF**. Open the Excel file: try the filter arrows, scroll (headers stay), check the totals row formulas.

## Tests

```powershell
cd D:\claude\attendance-system\backend
.\.venv\Scripts\python -m pytest
```

Expected `310 passed` (25 export tests open the files and check sheets, frozen panes, filters, formats, formulas, formula-injection protection, PDF text, Nigerian letters, every report in both formats, manager scope, audit record).

```powershell
cd D:\claude\attendance-system\dashboard
npm.cmd test
```

Expected `Tests 20 passed`.
