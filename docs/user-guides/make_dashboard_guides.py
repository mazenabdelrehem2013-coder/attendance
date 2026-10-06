r"""Builds the English guides for the Raya Attendance WEB DASHBOARD (for HR, admins and managers):
  1. Dashboard Guide    (first-time setup in the right order, the daily routine, troubleshooting)
  2. Dashboard Options  (every page, tab, button and setting, with screenshots)
Screenshots (docs/user-guides/img/dashboard) show the demo data of a test copy, not real employees.
    backend\.venv\Scripts\python docs\user-guides\make_dashboard_guides.py
"""

from make_user_guides import HERE, IMG, chip, msg, page, table, ui
from pdf_via_cdp import print_pdf

SITE = "https://raya.34.35.174.159.nip.io"
SHOTS = IMG / "dashboard"

WIDE_CSS = """
figure.wide { width: 100%; margin: 8px 0 14px; break-inside: avoid; text-align: center; }
figure.wide img { width: 100%; border: 1px solid #c9d1db; border-radius: 6px; box-shadow: 0 2px 8px rgba(0,0,0,.15); }
.wide figcaption { font-size: 8.5pt; color: #5f6b78; margin-top: 3px; }
.half { display: flex; gap: 12px; }
.half .wide { flex: 1; }
.check { list-style: none; padding-inline-start: 0; }
.check li { padding-inline-start: 26px; position: relative; margin-bottom: 6px; }
.check li::before { content: ''; position: absolute; left: 2px; top: 3px; width: 13px; height: 13px; border: 2px solid #1F5FAD; border-radius: 3px; }
"""


def shot(name: str, caption: str, width: str = "100%") -> str:
    return (f"<figure class='wide'><img src='{(SHOTS / name).as_uri()}' style='width:{width}'>"
            f"<figcaption>{caption}</figcaption></figure>")


def link(url: str) -> str:
    return f"<b dir='ltr'>{url}</b>"


def doc(title: str, subtitle: str, body: str) -> str:
    html = page("en", title, subtitle, body)
    return html.replace("</style>", WIDE_CSS + "</style>", 1)


# =============================================================================================
# 1. DASHBOARD GUIDE
# =============================================================================================


def guide_en() -> str:
    body = f"""
<div class='box'><b>The web dashboard</b> is where HR, administrators and managers run the attendance system:
add employees and workplaces, approve phones, review suspicious check-ins and download reports.
Employees do not use it: they only use the <b>Raya Attendance</b> phone app.<br>
Address: {link(SITE)} &nbsp;·&nbsp; works in any modern browser (Chrome, Edge, Safari, Firefox) on a computer.</div>

<h2>Who sees what</h2>
{table(["Role", "What they can do in the dashboard"], [
    [chip('b', 'ADMIN'), "Everything, including security settings, data retention and the audit log."],
    [chip('b', 'HR'), "Everything for daily work: employees, workplaces, phones, review, holidays &amp; leave, reports, settings."],
    [chip('g', 'MANAGER'), "Their <b>own team only</b>: today's attendance, history and reports of the people they manage."],
    [chip('n', 'EMPLOYEE'), "No dashboard access. They check in with the phone app."],
])}

<h2>1. Log in the first time</h2>
<ol>
<li>Open {link(SITE)} and enter your email (or employee ID) and the temporary password HR or IT gave you.</li>
<li>The dashboard asks you to <b>choose your own password</b> (at least 10 characters, not your name or email). Keep it private.</li>
<li>After 5 wrong passwords the account is locked for 15 minutes. Forgot it? Another HR user or the admin uses
{ui('RESET PASSWORD')} on the Employees page.</li>
</ol>
{shot("00-login-card.png", "Login page", "42%")}

<h2 class='pb'>2. First-time setup – do it in this order</h2>
<p>Each step needs the one before it (a workplace needs a branch and working hours, an employee needs a workplace…).</p>
<ul class='check'>
<li><b>Branch</b> – {ui('Locations &amp; departments')} → tab {ui('BRANCHES')}: at least one, e.g. <i>Head office</i>.</li>
<li><b>Working hours</b> – tab {ui('WORKING HOURS')}: e.g. <i>Standard 09:00–18:00 Mon–Sat</i>, with the grace minutes
(how late someone may arrive before counting as <i>late</i>; default 15).</li>
<li><b>Workplaces (locations)</b> – tab {ui('LOCATIONS')} → {ui('ADD LOCATION')}: name, short code, branch, the exact
position of the entrance, radius and time zone (see the box below).</li>
<li><b>Departments</b> – tab {ui('DEPARTMENTS')}: e.g. <i>Sales, Finance, HR</i>.</li>
<li><b>Managers first, then employees</b> – {ui('Employees')} → {ui('ADD EMPLOYEE')}. Create the managers first so you can choose
them as the manager of the others. Choose each person's check-in workplace(s); the dashboard gives you their temporary password.</li>
<li><b>Holidays</b> – {ui('Holidays &amp; leave')}: add this year's public holidays so nobody is counted absent on them.</li>
<li><b>Phones</b> – when people log in to the app the first time, approve their phones in {ui('Phones')}.</li>
<li><b>Optional</b>: scheduled reports, office QR screens, security rules.</li>
</ul>

<div class='warn'><b>Getting the workplace position right (most common mistake)</b>
<ol>
<li>In Google Maps, find the office and <b>right-click the entrance</b> of the building.</li>
<li>Click the two numbers at the top of the menu – they are copied (e.g. <span dir='ltr'>6.613119, 3.344065</span>).</li>
<li>Paste them into the <b>Latitude</b> box: the dashboard fills Latitude and Longitude automatically.</li>
<li><b>Radius</b>: 100–200 m suits most offices (between 10 and 5000).</li>
<li><b>Time zone</b>: the city of the office, written exactly like <span dir='ltr'>Africa/Lagos</span> or
<span dir='ltr'>Africa/Cairo</span> (not the server's time zone).</li>
</ol>
If check-ins show a distance of kilometres although people are at the office, the position of the workplace is wrong – edit it.</div>
{shot("16-add-location.png", "Add location")}

<h2 class='pb'>3. Adding an employee</h2>
<ol>
<li>{ui('Employees')} → {ui('ADD EMPLOYEE')}.</li>
<li>Fill in <b>Full name</b>, <b>Employee ID</b> (what they type in the app, e.g. EMP-0101), work email, phone (optional),
<b>Role</b> (Employee, Manager, HR, Admin), department and manager.</li>
<li><b>Check-in locations</b>: the workplaces where this person may check in – the first one is their main workplace.</li>
<li>Click {ui('CREATE')}. The dashboard shows a <b>temporary password – only once</b>. Copy it and give it to the
employee privately together with their employee ID. The app makes them choose their own password at the first login.</li>
<li>The employee installs <b>Raya Attendance</b> from Google Play and logs in.</li>
</ol>
{shot("14-add-employee.png", "Add employee")}

<h2 class='pb'>4. Approving a phone (once per employee)</h2>
<p>For security, each employee can only check in from <b>one approved phone</b>, and one phone can belong to only one
employee. After the first login the app shows <i>waiting for HR approval</i>.</p>
<ol>
<li>Open {ui('Phones')} → tab {ui('WAITING FOR APPROVAL')}.</li>
<li>Check that the name and phone model are right (ask the employee if unsure) and click {ui('APPROVE')}.
{ui('REJECT')} if you don't recognise the request.</li>
<li>The employee taps <i>Check again</i> in the app – the CHECK IN button turns green.</li>
</ol>
<div class='tip'>New phone or reinstalled app = a new approval. Approving the new phone switches off the old one automatically.</div>
{shot("19-all-phones.png", "Phones – all phones")}

<h2 class='pb'>5. Your daily routine (5 minutes)</h2>
{table(["When", "What to do", "Where"], [
    ["Morning (after 09:30)", "Look at who is present, late, absent or still missing.", f"{ui('Dashboard')}, {ui('Attendance')}"],
    ["Morning", "Approve or reject flagged check-ins from the previous day.", ui('Suspicious activity')],
    ["Whenever someone is new or changed phone", "Approve the phone.", ui('Phones')],
    ["When someone is on leave", "Record the leave so they are not counted absent.", f"{ui('Holidays &amp; leave')} → {ui('LEAVE')}"],
    ["Daily / weekly / monthly", "Download the reports (or let them be prepared automatically).", f"{ui('Reports')}, {ui('Scheduled reports')}"],
    ["Weekly", "Check open security alerts.", ui('Security monitoring')],
])}

<h2>6. Reviewing a flagged check-in</h2>
<p>When a check fails (for example the phone was outside the office radius, or a fake-GPS app was found) the check-in is
<b>flagged</b>: it is saved but <b>does not count</b> until HR decides. The employee only sees <i>waiting for HR review</i>.</p>
<ol>
<li>{ui('Suspicious activity')} → {ui('WAITING FOR REVIEW')} and click a row.</li>
<li>Read the <b>Checks</b> (what passed and what failed), the distance and accuracy; {ui('Open position on map')} shows where the phone was.</li>
<li>{ui('Approve – counts as attendance')} if the person really was at work, or {ui('REJECT')} with a short note.</li>
</ol>
{shot("18-review-detail.png", "Review a flagged check-in")}
<div class='box'>Every decision is saved with your name in the <b>audit log</b>. You cannot review your own attendance.</div>

<h2 class='pb'>7. Reports</h2>
<ul>
<li><b>Create a report</b> ({ui('Reports')}): choose the type (daily, weekly, monthly, late arrivals, absences, suspicious
attendance or a custom period), the date and optional filters, then {ui('DOWNLOAD EXCEL')} or {ui('DOWNLOAD PDF')}.</li>
<li><b>Ready reports</b>: reports prepared automatically by your scheduled reports, ready to download – also available
to managers and HR in the phone app.</li>
<li>Managers only ever get their own team.</li>
</ul>

<h2>8. Troubleshooting</h2>
{table(["Problem", "What to do"], [
    ["Check-ins show a distance of km although people are in the office",
     "The workplace position is wrong: {0} → Locations → EDIT, paste the right coordinates (section 2).".format(ui('Locations &amp; departments'))],
    [f"Saving a form shows {msg('Some fields are missing or invalid.')}",
     "The message ends with the field that is wrong, e.g. <i>timezone: unknown timezone</i>. Codes: letters/numbers only, no spaces."],
    ["An employee can't press CHECK IN (grey)", "Their phone is waiting for approval → Phones. Or they have no workplace → Employees → LOCATIONS."],
    ["An employee forgot the password / is locked", f"{ui('Employees')} → {ui('RESET PASSWORD')} gives a new temporary password."],
    ["Someone was counted absent while on leave or a holiday", f"Record the leave / holiday in {ui('Holidays &amp; leave')}."],
    ["A check-in was flagged by mistake", f"Approve it in {ui('Suspicious activity')}. If it happens often, check the workplace radius or {ui('Security settings')}."],
    ["The dashboard says the session expired", "Log in again (you are logged out after a period without activity)."],
])}
<div class='footer'>Raya Attendance web dashboard · version 1.0 · Screenshots show demo data from a test copy, not real employees.
The full list of pages and options is in the separate <b>Dashboard Options</b> PDF.</div>
"""
    return doc("Raya Attendance — Web Dashboard Guide", "First-time setup, daily routine and troubleshooting for HR and managers", body)


# =============================================================================================
# 2. DASHBOARD OPTIONS
# =============================================================================================


def section(title: str, image: str, caption: str, intro: str, rows: list[list[str]], extra: str = "", page_break: bool = True) -> str:
    pb = " class='pb'" if page_break else ""
    return (f"<h2{pb}>{title}</h2><p>{intro}</p>{shot(image, caption)}"
            f"{table(['Option', 'What it does'], rows) if rows else ''}{extra}")


def options_en() -> str:
    parts = [
        f"""<div class='box'>This reference explains every page of the web dashboard ({link(SITE)}) from top to bottom.
For the setup order and the daily routine, see the <b>Dashboard Guide</b>. Pages marked <b>HR</b> are visible to HR and
admins; managers see the Dashboard (their team) and Reports.</div>
<h2>The frame around every page</h2>
{table(['Part', 'What it does'], [
    ['Menu (left)', 'Goes to each page. A red number shows how many items wait for you (e.g. check-ins to review, open security alerts).'],
    ['Bell (top right)', 'Notifications: new flagged check-ins, phones waiting for approval, security alerts, ready reports. Click to read them.'],
    ['Your name · role (top right)', f"Menu with {ui('Change password')} and {ui('Log out')}."],
])}""",
        section("Dashboard (company overview)", "01-overview.png", "Dashboard",
                "The first page: how today looks for the whole company (managers: their team).",
                [["Date", "Pick another day to see it."],
                 ["Cards", "Employees, Present, Late, Absent, Checked in now, Missing check-out, Suspicious attempts, Rejected attempts, Waiting for review."],
                 ["Charts", "Attendance by location and by department, late arrivals and absences over the last 30 days, monthly attendance rate."]]),
        section("Attendance", "02-attendance.png", "Attendance – every employee for one day",
                "One line per employee for the chosen day.",
                [["Date / refresh", "Choose the day; the circular arrow reloads."],
                 [ui('EXPORT CSV'), "Downloads the list for Excel."],
                 ["Search and filters", "Name or ID, department, location, status."],
                 ["Status", f"{chip('g','Present')} {chip('a','Late')} {chip('r','Absent')} {chip('p','Pending review')} {chip('n','Not checked in')} {chip('b','On leave')} – plus whether the person is checked in now."],
                 ["Verification", f"{chip('g','Verified')} all checks passed; otherwise the check-in waits for review."]]),
        section("Suspicious activity (HR)", "03-suspicious-activity.png", "Suspicious activity",
                "Check-ins and check-outs that failed a check. They don't count until approved.",
                [[ui('WAITING FOR REVIEW'), "Flagged items to decide. Click a row for the details."],
                 [ui('REVIEWED'), "Items already approved or rejected, with who decided."],
                 [ui('REJECTED ATTEMPTS'), "Attempts the system refused outright (never counted)."],
                 [ui('SECURITY EVENTS'), "Technical events: fake-GPS apps, modified apps, impossible travel, failed logins…"],
                 ["Reason / Distance / Risk", "Why it was flagged, how far from the office, and a 0–100 risk score."]],
                shot("18-review-detail.png", "Details: the checks, the position on the map, and Approve / Reject (a note is required to reject)")),
        section("Employees (HR)", "04-employees.png", "Employees",
                "Everyone who can log in to the app or the dashboard.",
                [[ui('ADD EMPLOYEE'), f"Creates a person: full name, employee ID, email, phone, role, department, manager, check-in locations. After {ui('CREATE')} the temporary password is shown <b>once</b> – give it to the employee privately."],
                 [ui('EDIT'), "Changes details, role, manager, and the employment status (Active / Suspended / Terminated) and whether they can log in."],
                 [ui('LOCATIONS'), "Where this person may check in; the first (★) is the main workplace."],
                 [ui('RESET PASSWORD'), "Creates a new temporary password (shown once) and logs the person out everywhere; they must choose a new password at the next login."],
                 ["Search", "By name, ID or email."]],
                shot("14-add-employee.png", "Add employee") + shot("15-employee-locations.png", "Check-in locations of an employee")),
        section("Locations &amp; departments (HR)", "05-locations.png", "Organization – Locations",
                "The structure of the company.",
                [[ui('LOCATIONS'), "Workplaces: name, code, address, position (latitude, longitude), allowed radius, time zone, working hours, active or not."],
                 [ui('DEPARTMENTS'), "Departments (name and code)."],
                 [ui('WORKING HOURS'), "Schedules: working days, start/end time, grace minutes (late after), early leave allowed."],
                 [ui('BRANCHES'), "Groups of locations (e.g. per city or region). A location belongs to one branch."]],
                shot("16-add-location.png", "Add location – paste the Google Maps pair into Latitude")
                + shot("17-working-hours.png", "Working hours")),
        section("Phones (HR)", "19-all-phones.png", "Phones",
                "Each employee checks in from one approved phone; one phone belongs to one employee.",
                [[ui('WAITING FOR APPROVAL'), f"New phones after a first login: {ui('APPROVE')} or {ui('REJECT')}."],
                 [ui('ALL PHONES'), "Every registered phone: employee, model, Android version, app version, last used, status. Approving a new phone switches off the old one."]]),
        section("QR screens (HR, optional)", "07-qr-screens.png", "Office QR screens",
                f"For extra proof of presence, a screen or tablet in the office shows a QR code that changes every 30 seconds; "
                f"employees scan it when they check in. Open {link(SITE + '/qr-display')} on that screen and type its key, then set the location to "
                f"<i>GPS + office QR code</i> in {ui('Security settings')}.",
                [[ui('ADD SCREEN'), "Creates a screen for a location and shows its key once – copy it to the screen."],
                 [ui('NEW KEY'), "Replaces the key (e.g. if the screen was replaced)."],
                 [ui('DISABLE'), "Switches the screen off."],
                 ["Last contact", "When the screen last asked for a code; orange/red means it is offline."]]),
        section("Holidays &amp; leave (HR)", "08-holidays-leave.png", "Holidays & leave",
                "People on leave or on a holiday are not counted as absent.",
                [[ui('HOLIDAYS'), f"Public holidays per year: {ui('ADD HOLIDAY')} (date, name, all locations or one). Moving holidays (Eid, Easter…) must be added every year."],
                 [ui('LEAVE'), f"{ui('RECORD LEAVE')}: employee, type (annual, sick, maternity, paternity, official duty, unpaid, other), from, to, note."]],
                shot("20-leave.png", "Leave")),
        section("Reports", "09-reports.png", "Reports – create a report",
                "Download attendance as Excel or PDF. Managers get their own team only. Every download is recorded in the audit log.",
                [["Report", "Daily, weekly, monthly, late arrivals, absences, suspicious attendance, or a custom period for an employee / location / department / manager."],
                 ["Date / period and filters", "Location, department, manager."],
                 [f"{ui('DOWNLOAD EXCEL')} / {ui('DOWNLOAD PDF')}", "Creates and downloads the file."],
                 [ui('READY REPORTS'), "Files prepared automatically by scheduled reports – click to download."]],
                shot("21-ready-reports.png", "Ready reports")),
        section("Scheduled reports &amp; alerts (HR)", "10-scheduled-reports.png", "Scheduled reports",
                "Reports created automatically at set times (nothing is emailed); they appear under Ready reports in the dashboard and the app.",
                [[ui('NEW SCHEDULED REPORT'), "Name, report type, how often (daily / weekly / monthly), days and time, what it covers (today so far or the previous working day), location/department filter, files (Excel, PDF), who sees it."],
                 [ui('CREATE NOW'), "Makes the report immediately."],
                 [f"{ui('EDIT')} / {ui('DELETE')}", "Changes or removes the schedule (or pause it)."],
                 [ui('ALERTS'), "Which events appear under the bell, and for whom (HR, admins, the employee's own manager): check-in needs review, check-in rejected, new phone waiting for approval, late arrival, missing check-out, frequent absence… Changes are saved straight away."]],
                shot("23-new-scheduled-report.png", "New scheduled report")),
        section("Security monitoring (admin)", "11-security.png", "Security monitoring",
                "An overview of security over the last 30 days.",
                [[ui('OVERVIEW'), f"Open alerts, security events, failed logins, locked accounts, and the audit-log check ({ui('CHECK NOW')}) that proves no record was changed or deleted."],
                 [ui('ALERTS'), f"Alerts raised by the rules: mark {ui('I&#39;m checking it')} or {ui('Resolve')}."],
                 [ui('ALERT RULES'), "When an alert is raised (e.g. many failed logins from one address, repeated fake GPS) and how serious it is."],
                 [ui('DATA RETENTION'), "How long each kind of data is kept before it is removed automatically (e.g. exact GPS positions 1 year, attendance 7 years)."]],
                shot("22-alert-rules.png", "Alert rules")),
        section("Audit log (admin)", "12-audit-log.png", "Audit log",
                "Every change made by staff – who, what, when, before and after. Entries can't be edited or deleted.",
                [["Filters", "Search person or object, action, from / to date."],
                 ["Click an entry", "Shows each changed field with the old and new value."]]),
        section("Security settings (HR)", "13-settings.png", "Security settings",
                "How strict the check-in checks are – for the whole company or one location.",
                [["Rules for", "The whole company (default) or a single location (or <i>Use company rules</i>)."],
                 ["Verification method", "GPS only, or GPS + office QR code."],
                 ["When a check fails", f"For each check – outside the office radius, weak GPS, old GPS reading, fake-GPS app, phone clock changed, impossible travel speed, app/phone integrity, office QR – choose {chip('g','Allow (record only)')} {chip('a','Flag for HR review')} or {chip('r','Reject')}."],
                 ["Limits", "Worst accepted GPS accuracy, oldest accepted GPS reading, time to complete a check-in, highest believable travel speed, allowed phone clock difference."],
                 ["Count flagged attendance before review", "If on, flagged check-ins count until HR rejects them (default: off)."]],
                "<div class='footer'>Raya Attendance web dashboard · version 1.0 · Screenshots show demo data from a test copy, not real employees.</div>"),
    ]
    return doc("Raya Attendance — Web Dashboard Options", "Every page, tab, button and setting of the dashboard", "".join(parts))


def render(html: str, name: str) -> None:
    src = HERE / f"{name}.html"
    src.write_text(html, encoding="utf-8")
    pdf = HERE / f"{name}.pdf"
    print_pdf(src, pdf)
    src.unlink()
    print(pdf.name, f"{pdf.stat().st_size // 1024} KB")


def main() -> None:
    render(guide_en(), "Raya-Attendance-Dashboard-Guide-EN")
    render(options_en(), "Raya-Attendance-Dashboard-Options-EN")


if __name__ == "__main__":
    main()
