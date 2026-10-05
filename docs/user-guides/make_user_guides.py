r"""Builds the end-user guides of the Raya Attendance app as PDF, in English and Arabic:
  1. Guide & Walkthrough   (how to use the app, step by step, with screenshots, troubleshooting)
  2. App Options           (every screen, button, status and message of the app)
Printed by Microsoft Edge (headless), which shapes Arabic text correctly.
    backend\.venv\Scripts\python docs\user-guides\make_user_guides.py
"""

import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
IMG = HERE / "img"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
BLUE = "#1F5FAD"


def ui(text: str) -> str:
    """A button / menu / screen name exactly as written in the (English) app."""
    return f"<span class='ui' dir='ltr'>{text}</span>"


def msg(text: str) -> str:
    return f"<span class='msg' dir='ltr'>{text}</span>"


def img(name: str) -> str:
    return (IMG / name).as_uri()


CSS = f"""
@page {{ size: A4; margin: 14mm 13mm 16mm; }}
* {{ box-sizing: border-box; }}
body {{ font-family: 'Segoe UI', Tahoma, Arial, sans-serif; color: #1d2733; font-size: 10.6pt; line-height: 1.6; }}
h1 {{ color: {BLUE}; font-size: 22pt; margin: 0; line-height: 1.2; }}
h2 {{ color: {BLUE}; font-size: 14pt; border-bottom: 2px solid {BLUE}; padding-bottom: 3px; margin: 24px 0 10px; break-after: avoid; }}
h3 {{ font-size: 11.5pt; margin: 0 0 4px; }}
.cover {{ display: flex; gap: 18px; align-items: center; margin-bottom: 10px; }}
.cover img {{ width: 92px; height: 92px; border-radius: 22px; }}
.sub {{ color: #5f6b78; margin-top: 4px; }}
.ui {{ display: inline-block; background: #e8f0fa; color: {BLUE}; font-weight: 700; border-radius: 4px; padding: 0 6px; unicode-bidi: isolate; }}
.msg {{ color: #8a3b12; background: #fff4e5; border-radius: 4px; padding: 0 5px; unicode-bidi: isolate; }}
.box {{ background: #f4f7fb; border: 1px solid #d5dbe3; border-radius: 8px; padding: 9px 14px; margin: 8px 0; }}
.tip {{ background: #eaf6ee; border: 1px solid #b9dcc3; border-radius: 8px; padding: 9px 14px; margin: 8px 0; }}
.warn {{ background: #fff4e5; border: 1px solid #f0c27b; border-radius: 8px; padding: 9px 14px; margin: 8px 0; }}
.step {{ display: flex; gap: 20px; align-items: flex-start; margin: 14px 0; break-inside: avoid; }}
.step .text {{ flex: 1; }}
.step .num {{ display: inline-block; width: 26px; height: 26px; line-height: 26px; text-align: center; background: {BLUE}; color: #fff; border-radius: 50%; font-weight: 700; margin-inline-end: 8px; }}
.shots {{ flex: none; display: flex; gap: 10px; }}
figure {{ margin: 0; width: 168px; text-align: center; }}
figure img {{ width: 100%; border-radius: 14px; border: 1px solid #c9d1db; box-shadow: 0 3px 10px rgba(0,0,0,.18); }}
figcaption {{ font-size: 8.5pt; color: #5f6b78; margin-top: 3px; line-height: 1.3; }}
table {{ border-collapse: collapse; width: 100%; margin: 6px 0; break-inside: auto; }}
tr {{ break-inside: avoid; }}
th, td {{ border: 1px solid #d5dbe3; padding: 5px 8px; vertical-align: top; text-align: start; font-size: 9.8pt; }}
th {{ background: #eef3f9; }}
ul, ol {{ margin: 4px 0; padding-inline-start: 22px; }}
li {{ margin-bottom: 3px; }}
.pb {{ break-before: page; }}
.chip {{ display: inline-block; border-radius: 12px; padding: 0 9px; font-weight: 600; font-size: 9.4pt; border: 1px solid; white-space: nowrap; }}
.g {{ color: #1E8E3E; background: #e6f4ea; border-color: #1E8E3E; }}
.b {{ color: #1F5FAD; background: #e8f0fa; border-color: #1F5FAD; }}
.a {{ color: #B35C00; background: #fff1e0; border-color: #E37400; }}
.p {{ color: #8E44AD; background: #f3e8f8; border-color: #8E44AD; }}
.r {{ color: #C5221F; background: #fdeceb; border-color: #C5221F; }}
.n {{ color: #5F6368; background: #eceff1; border-color: #5F6368; }}
.map {{ position: relative; flex: none; width: 250px; }}
.map img {{ width: 100%; border-radius: 16px; border: 1px solid #c9d1db; box-shadow: 0 3px 10px rgba(0,0,0,.18); }}
.map i {{ position: absolute; width: 24px; height: 24px; line-height: 24px; border-radius: 50%; background: #d93025; color: #fff; font-style: normal; font-weight: 700; font-size: 10pt; text-align: center; border: 2px solid #fff; box-shadow: 0 1px 4px rgba(0,0,0,.4); }}
.footer {{ color: #5f6b78; font-size: 9pt; margin-top: 22px; border-top: 1px solid #d5dbe3; padding-top: 6px; }}
"""


def page(lang: str, title: str, subtitle: str, body: str) -> str:
    d = "rtl" if lang == "ar" else "ltr"
    return (f"<!doctype html><html lang='{lang}' dir='{d}'><head><meta charset='utf-8'><style>{CSS}</style></head><body>"
            f"<div class='cover'><img src='{img('icon.png')}'><div><h1>{title}</h1><div class='sub'>{subtitle}</div></div></div>"
            f"{body}</body></html>")


def fig(name: str, caption: str) -> str:
    return f"<figure><img src='{img(name)}'><figcaption>{caption}</figcaption></figure>"


def step(n: int, title: str, body: str, figs: list[tuple[str, str]]) -> str:
    shots = "".join(fig(a, b) for a, b in figs)
    return (f"<div class='step'><div class='text'><h3><span class='num'>{n}</span>{title}</h3>{body}</div>"
            f"<div class='shots'>{shots}</div></div>")


def table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def chip(kind: str, text: str) -> str:
    return f"<span class='chip {kind}' dir='ltr'>{text}</span>"


# =============================================================================================
# 1. GUIDE & WALKTHROUGH
# =============================================================================================


def walkthrough_en() -> str:
    steps = "".join([
        step(1, "Log in",
             f"<p>Open <b>Raya Attendance</b>. Type your <b>employee ID</b> (for example EMP-0101) or your work email, then your "
             f"password, and tap {ui('LOG IN')}. The eye icon shows or hides the password.</p>"
             f"<p>Forgot it? Ask HR to reset it. After <b>5 wrong passwords</b> the account is locked for 15 minutes.</p>",
             [("login.png", "Login screen")]),
        step(2, "Choose your own password (first login only)",
             f"<p>HR gives you a <b>temporary password</b>. The first time, the app asks you to replace it: type the temporary "
             f"password, then your new password twice, and tap {ui('SAVE PASSWORD')}.</p>"
             f"<ul><li>At least <b>10 characters</b>.</li><li>Different from the temporary password.</li>"
             f"<li>Do not use your name, employee ID or the first part of your email.</li></ul>"
             f"<div class='tip'>Keep your password private. Nobody from HR or IT will ever ask for it.</div>",
             [("password.png", "Change password")]),
        step(3, "Your phone must be approved by HR (once)",
             f"<p>The first time you log in, the app registers <b>this phone</b>. You will see the orange notice "
             f"{msg('This phone is waiting for HR approval…')} and the {ui('CHECK IN')} button stays grey.</p>"
             f"<p>Tell HR that you registered your phone. When they approve it, tap {ui('Check again')}: the notice disappears and the button turns <b>green</b> (CHECK IN is green, CHECK OUT is red).</p>"
             f"<div class='box'><b>Why?</b> So that one phone cannot be used to check in for several people. "
             f"A new phone (or reinstalling the app) needs a new approval.</div>",
             [("home.png", "Waiting for HR approval")]),
        step(4, "Check in",
             f"<p>When you are at your workplace and your phone is approved, tap {ui('CHECK IN')}.</p>"
             f"<ol><li>The first time, Android asks for permission: choose <b>Location → While using the app</b> "
             f"(and <b>Camera</b> if your office uses a QR code).</li>"
             f"<li>The button shows {msg('Preparing…')}, {msg('Getting your location…')}, {msg('Verifying…')}. Wait a few seconds.</li>"
             f"<li>If your office has a QR screen, point the camera at it. The code <b>changes every 30 seconds</b>.</li>"
             f"<li>A card shows the result: <b>Checked in</b> (green), with the time and office. Tap {ui('OK')}.</li></ol>"
             f"<div class='tip'>Turn Location on <b>before</b> you tap. Near a window or outdoors, GPS is faster and more accurate.</div>",
             [("result-ok.png", "The result card (here for a check-out)")]),
        step(5, "During the day",
             f"<p>The home screen shows <b>Today's status</b>, your working hours, your <b>first check-in</b> and the time <b>worked</b>.</p>"
             f"<ul><li>You may check out and in again several times a day (for example, lunch).</li>"
             f"<li>Only completed visits (a check-in followed by a check-out) count as worked hours.</li>"
             f"<li>{ui('Today’s attempts')} lists everything you tried today and what happened.</li></ul>",
             []),
        step(6, "Check out",
             f"<p>When you leave, tap {ui('CHECK OUT')}. The steps are the same as for check-in.</p>"
             f"<div class='warn'><b>Forgot to check out?</b> At night the system marks that visit <b>Missing check-out</b> and its hours "
             f"are not counted. Tell your manager or HR the same day.</div>",
             []),
        step(7, "“Recorded – pending review”",
             f"<p>Sometimes the system is not completely sure (for example weak GPS or a very unusual position). Your check-in is "
             f"<b>not rejected</b>: it is recorded and <b>HR reviews it</b>. Hours may not count until HR approves. "
             f"You do not need to do anything, but HR may contact you.</p>",
             [("result-pending.png", "Recorded – pending review")]),
        step(8, "My attendance (history)",
             f"<p>Tap the <b>calendar icon</b> at the top right. You see the month with the number of days <b>Present</b>, <b>Late</b> "
             f"and total hours <b>Worked</b>, and every day with its times, hours, office and status. Use the arrows to change month.</p>",
             [("history.png", "My attendance")]),
        step(9, "Change password or log out",
             f"<p>Tap the <b>three dots (⋮)</b> at the top right: {ui('Change password')} or {ui('Log out')}. "
             f"Changing your password logs you out on other devices. Log out if you give your phone to someone else.</p>",
             [("menu.png", "Menu")]),
    ])
    routine = (f"<div class='box'><b>Your day in five steps:</b> arrive at work → open the app → tap {ui('CHECK IN')} → work → "
               f"tap {ui('CHECK OUT')} when you leave.</div>")
    rows = [
        [msg("You appear to be outside your assigned work location."), "The GPS puts you outside the allowed area of your office.",
         "Move closer to or inside the office, wait a few seconds and try again. If you are inside and it keeps failing, tell HR."],
        [msg("Your location signal is weak. Move to an open area or near a window and try again."), "GPS accuracy is too low (common in basements and thick buildings).",
         "Go near a window or outside, make sure Location is on, and try again."],
        [msg("Location is turned off. Turn on Location in your phone settings and try again."), "Location is switched off on the phone.",
         "Swipe down and turn <b>Location</b> on, then tap CHECK IN again."],
        [msg("Location needed") + " / " + msg("Location permission is blocked…"), "The app is not allowed to use your location.",
         f"Tap {ui('Open settings')} → <b>Permissions → Location → Allow only while using the app</b>."],
        [msg("Camera permission is needed to scan the office code…"), "Your office uses a QR code and the camera is blocked.",
         "Allow <b>Camera</b> for the app in the phone settings."],
        [msg("We couldn't verify this attendance. Please contact HR."), "The security checks could not confirm this attempt.",
         "Do not keep retrying. Contact HR and tell them the time."],
        [msg("This phone can't be used for attendance. Please contact HR."), "HR rejected or switched off this phone.", "Contact HR. They can approve a new registration."],
        [msg("You are already checked in. Check out first."), "You are already checked in.", f"Tap {ui('CHECK OUT')} first."],
        [msg("You are not checked in."), "You tried to check out without a check-in.", "Check in first."],
        [msg("You have no active work location. Please contact HR."), "Home shows " + msg("None assigned - contact HR") + ".", "Ask HR to assign your workplace."],
        [msg("This request expired. Please try again."), "Too much time passed during the attempt.", "Tap the button again."],
        [msg("Can't reach the server. Check your internet connection and try again."), "No internet. Check-in does not work offline.", "Turn on mobile data or Wi-Fi and try again."],
        [msg("Too many failed attempts. Try again in N minute(s)."), "Wrong password 5 times: the account is locked for 15 minutes.", "Wait, or ask HR to reset your password."],
        [msg("Your session has expired. Please log in again."), "You were logged out for safety.", "Log in again."],
    ]
    trouble = table(["Message on the screen", "What it means", "What to do"], rows)
    privacy = ("<ul><li>Your location is read <b>only at the moment you tap Check in or Check out</b>. There is no tracking and no background location.</li>"
               "<li>The camera is used only to read the office QR code. No photos are taken or saved.</li>"
               "<li>Your manager sees only your team; HR sees everyone. Nobody else can see your attendance.</li>"
               "<li><b>Do not use fake-GPS (“mock location”) apps</b> or developer mock-location settings, and do not use rooted or modified phones. "
               "Such check-ins are flagged and reviewed by HR.</li></ul>")
    managers = (f"<p>Managers and HR also see a <b>chart icon</b> next to the calendar. It opens <b>Reports</b>: create a daily, weekly, "
                f"monthly, late-arrivals or absence report for your team (HR: for everyone) and download it as <b>Excel</b> or <b>PDF</b>, "
                f"or open a report that was prepared automatically ({ui('Ready reports')}). Files are saved in the phone's "
                f"<b>Downloads/Attendance</b> folder. See the <i>App Options</i> guide for details.</p>")
    body = (
        "<h2>What you need</h2><ul><li>An <b>Android phone</b> (Android 8.0 or newer) with internet.</li>"
        "<li>Your <b>employee ID</b> (or work email) and the <b>temporary password</b> from HR.</li>"
        "<li><b>Location (GPS)</b> switched on.</li><li>To be <b>at your workplace</b> when you check in.</li></ul>"
        "<h2>Install</h2><p>Open <b>Google Play</b>, search for <b>Raya Attendance</b> and tap <b>Install</b>. "
        "(During the test period HR may send you an invitation link instead.)</p>" + routine +
        "<h2>Walkthrough</h2>" + steps +
        "<h2>If something goes wrong</h2>" + trouble +
        "<h2>Your privacy and fairness</h2>" + privacy +
        "<h2>For managers and HR</h2>" + managers +
        "<div class='footer'>Need help? Contact the Raya HR department. This guide describes version 1.0 of the app.</div>")
    return page("en", "Raya Attendance — User Guide &amp; Walkthrough", "For employees · Android app · Version 1.0", body)


def walkthrough_ar() -> str:
    steps = "".join([
        step(1, "تسجيل الدخول",
             f"<p>افتح تطبيق <b>Raya Attendance</b>. اكتب <b>رقم الموظف</b> (مثل EMP-0101) أو بريدك الوظيفي، ثم كلمة المرور، "
             f"واضغط {ui('LOG IN')}. أيقونة العين تُظهر كلمة المرور أو تُخفيها.</p>"
             f"<p>نسيت كلمة المرور؟ اطلب من الموارد البشرية إعادة تعيينها. بعد <b>5 محاولات خاطئة</b> يُقفل الحساب لمدة 15 دقيقة.</p>",
             [("login.png", "شاشة تسجيل الدخول")]),
        step(2, "اختر كلمة مرورك الخاصة (عند أول دخول فقط)",
             f"<p>تعطيك الموارد البشرية <b>كلمة مرور مؤقتة</b>. في أول مرة يطلب التطبيق استبدالها: اكتب كلمة المرور المؤقتة ثم كلمة "
             f"المرور الجديدة مرتين، واضغط {ui('SAVE PASSWORD')}.</p>"
             f"<ul><li><b>10 أحرف على الأقل</b>.</li><li>مختلفة عن كلمة المرور المؤقتة.</li>"
             f"<li>لا تستخدم اسمك أو رقم الموظف أو الجزء الأول من بريدك.</li></ul>"
             f"<div class='tip'>حافظ على سرية كلمة المرور. لن يطلبها منك أحد من الموارد البشرية أو قسم تقنية المعلومات أبدًا.</div>",
             [("password.png", "تغيير كلمة المرور")]),
        step(3, "يجب أن توافق الموارد البشرية على هاتفك (مرة واحدة)",
             f"<p>عند أول تسجيل دخول يسجّل التطبيق <b>هذا الهاتف</b>. سيظهر إشعار برتقالي "
             f"{msg('This phone is waiting for HR approval…')} ويبقى زر {ui('CHECK IN')} رماديًا.</p>"
             f"<p>أبلغ الموارد البشرية أنك سجّلت هاتفك. بعد موافقتهم اضغط {ui('Check again')}: يختفي الإشعار ويتحوّل الزر إلى اللون <b>الأخضر</b> (CHECK IN أخضر وCHECK OUT أحمر).</p>"
             f"<div class='box'><b>لماذا؟</b> حتى لا يمكن استخدام هاتف واحد لتسجيل حضور عدة أشخاص. "
             f"الهاتف الجديد (أو إعادة تثبيت التطبيق) يحتاج موافقة جديدة.</div>",
             [("home.png", "في انتظار موافقة الموارد البشرية")]),
        step(4, "تسجيل الحضور",
             f"<p>عندما تكون في مقر عملك وهاتفك معتمد، اضغط {ui('CHECK IN')}.</p>"
             f"<ol><li>في أول مرة يطلب أندرويد صلاحية: اختر <b>الموقع (Location) ← أثناء استخدام التطبيق</b> "
             f"(وكذلك <b>الكاميرا</b> إذا كان مكتبك يستخدم رمز QR).</li>"
             f"<li>يعرض الزر {msg('Preparing…')} ثم {msg('Getting your location…')} ثم {msg('Verifying…')}. انتظر ثواني قليلة.</li>"
             f"<li>إذا كان في مكتبك شاشة QR، وجّه الكاميرا نحوها. الرمز <b>يتغيّر كل 30 ثانية</b>.</li>"
             f"<li>تظهر بطاقة النتيجة: <b>Checked in</b> (أخضر) مع الوقت والمكتب. اضغط {ui('OK')}.</li></ol>"
             f"<div class='tip'>شغّل خدمة الموقع <b>قبل</b> الضغط. بالقرب من نافذة أو في الخارج يكون GPS أسرع وأدق.</div>",
             [("result-ok.png", "بطاقة النتيجة (هنا عند تسجيل الانصراف)")]),
        step(5, "خلال اليوم",
             f"<p>تعرض الشاشة الرئيسية <b>حالة اليوم</b> وساعات العمل و<b>أول تسجيل حضور</b> والوقت <b>المعمول</b>.</p>"
             f"<ul><li>يمكنك تسجيل الانصراف والحضور مرة أخرى عدة مرات في اليوم (مثل استراحة الغداء).</li>"
             f"<li>تُحتسب فقط الزيارات المكتملة (حضور يليه انصراف) ضمن ساعات العمل.</li>"
             f"<li>القائمة {ui('Today’s attempts')} تعرض كل محاولاتك اليوم ونتيجتها.</li></ul>",
             []),
        step(6, "تسجيل الانصراف",
             f"<p>عند المغادرة اضغط {ui('CHECK OUT')}. الخطوات هي نفسها كما في تسجيل الحضور.</p>"
             f"<div class='warn'><b>نسيت تسجيل الانصراف؟</b> في الليل يضع النظام على هذه الزيارة علامة <b>Missing check-out</b> ولا تُحتسب "
             f"ساعاتها. أبلغ مديرك أو الموارد البشرية في اليوم نفسه.</div>",
             []),
        step(7, "«Recorded – pending review» (مسجَّل – قيد المراجعة)",
             f"<p>أحيانًا لا يكون النظام متأكدًا تمامًا (مثل ضعف GPS أو موقع غير معتاد). تسجيلك <b>لم يُرفض</b>: "
             f"هو مسجَّل و<b>تراجعه الموارد البشرية</b>. قد لا تُحتسب الساعات حتى توافق الموارد البشرية. "
             f"لا تحتاج لفعل شيء، لكن قد تتواصل معك الموارد البشرية.</p>",
             [("result-pending.png", "Recorded – pending review")]),
        step(8, "حضوري (السجل)",
             f"<p>اضغط <b>أيقونة التقويم</b> أعلى الشاشة. ترى الشهر مع عدد أيام <b>الحضور</b> و<b>التأخير</b> ومجموع الساعات <b>المعمولة</b>، "
             f"وكل يوم بأوقاته وساعاته ومكتبه وحالته. استخدم الأسهم لتغيير الشهر.</p>",
             [("history.png", "My attendance")]),
        step(9, "تغيير كلمة المرور أو تسجيل الخروج",
             f"<p>اضغط <b>النقاط الثلاث (⋮)</b> أعلى الشاشة: {ui('Change password')} أو {ui('Log out')}. "
             f"تغيير كلمة المرور يُخرجك من الأجهزة الأخرى. سجّل الخروج إذا أعطيت هاتفك لشخص آخر.</p>",
             [("menu.png", "القائمة")]),
    ])
    routine = (f"<div class='box'><b>يومك في خمس خطوات:</b> تصل إلى العمل ← تفتح التطبيق ← تضغط {ui('CHECK IN')} ← تعمل ← "
               f"تضغط {ui('CHECK OUT')} عند المغادرة.</div>")
    rows = [
        [msg("You appear to be outside your assigned work location."), "الـGPS يضعك خارج النطاق المسموح لمكتبك.",
         "اقترب من المكتب أو ادخل إليه، انتظر ثواني وأعد المحاولة. إذا كنت بالداخل واستمر الخطأ أبلغ الموارد البشرية."],
        [msg("Your location signal is weak. Move to an open area or near a window and try again."), "دقة الـGPS منخفضة (شائع في الأقبية والمباني السميكة).",
         "اقترب من نافذة أو اخرج، تأكد أن الموقع مُشغَّل، ثم أعد المحاولة."],
        [msg("Location is turned off. Turn on Location in your phone settings and try again."), "خدمة الموقع مُطفأة على الهاتف.",
         "اسحب الشاشة للأسفل وشغّل <b>الموقع (Location)</b> ثم اضغط CHECK IN مرة أخرى."],
        [msg("Location needed") + " / " + msg("Location permission is blocked…"), "التطبيق غير مسموح له باستخدام موقعك.",
         f"اضغط {ui('Open settings')} ← <b>الأذونات (Permissions) ← الموقع (Location) ← السماح أثناء استخدام التطبيق فقط</b>."],
        [msg("Camera permission is needed to scan the office code…"), "مكتبك يستخدم رمز QR والكاميرا محظورة.",
         "اسمح بـ<b>الكاميرا</b> للتطبيق من إعدادات الهاتف."],
        [msg("We couldn't verify this attendance. Please contact HR."), "فحوصات الأمان لم تستطع تأكيد هذه المحاولة.",
         "لا تكرر المحاولة كثيرًا. تواصل مع الموارد البشرية وأخبرهم بالوقت."],
        [msg("This phone can't be used for attendance. Please contact HR."), "رفضت الموارد البشرية هذا الهاتف أو أوقفته.", "تواصل مع الموارد البشرية؛ يمكنهم اعتماد تسجيل جديد."],
        [msg("You are already checked in. Check out first."), "أنت مسجَّل الحضور بالفعل.", f"اضغط {ui('CHECK OUT')} أولًا."],
        [msg("You are not checked in."), "حاولت تسجيل الانصراف دون تسجيل حضور.", "سجّل الحضور أولًا."],
        [msg("You have no active work location. Please contact HR."), "تظهر في الشاشة الرئيسية " + msg("None assigned - contact HR") + ".", "اطلب من الموارد البشرية تعيين مقر عملك."],
        [msg("This request expired. Please try again."), "مرّ وقت طويل أثناء المحاولة.", "اضغط الزر مرة أخرى."],
        [msg("Can't reach the server. Check your internet connection and try again."), "لا يوجد إنترنت. تسجيل الحضور لا يعمل دون اتصال.", "شغّل بيانات الهاتف أو Wi-Fi وأعد المحاولة."],
        [msg("Too many failed attempts. Try again in N minute(s)."), "5 محاولات كلمة مرور خاطئة: الحساب مقفل 15 دقيقة.", "انتظر، أو اطلب من الموارد البشرية إعادة تعيين كلمة المرور."],
        [msg("Your session has expired. Please log in again."), "تم تسجيل خروجك لأسباب أمنية.", "سجّل الدخول من جديد."],
    ]
    trouble = table(["الرسالة على الشاشة", "معناها", "ماذا تفعل"], rows)
    privacy = ("<ul><li>يُقرأ موقعك <b>فقط لحظة الضغط على تسجيل الحضور أو الانصراف</b>. لا يوجد تتبّع ولا موقع في الخلفية.</li>"
               "<li>تُستخدم الكاميرا فقط لقراءة رمز QR الخاص بالمكتب. لا تُلتقط ولا تُحفظ أي صور.</li>"
               "<li>مديرك يرى فريقه فقط، والموارد البشرية ترى الجميع. لا أحد غيرهم يرى حضورك.</li>"
               "<li><b>لا تستخدم تطبيقات الموقع الوهمي (Fake GPS / Mock location)</b> ولا إعدادات الموقع الوهمي للمطوّرين، ولا هواتف مفتوحة الجذر أو معدَّلة. "
               "تسجيلات الحضور هذه يتم تمييزها وتراجعها الموارد البشرية.</li></ul>")
    managers = (f"<p>يرى المديرون والموارد البشرية أيضًا <b>أيقونة مخطط</b> بجوار التقويم. تفتح <b>Reports</b>: أنشئ تقريرًا يوميًا أو أسبوعيًا أو شهريًا "
                f"أو تقرير التأخير أو الغياب لفريقك (الموارد البشرية: للجميع) ونزّله بصيغة <b>Excel</b> أو <b>PDF</b>، "
                f"أو افتح تقريرًا جُهّز تلقائيًا ({ui('Ready reports')}). تُحفظ الملفات في مجلد <b>Downloads/Attendance</b> على الهاتف. "
                f"التفاصيل في دليل <i>خيارات التطبيق</i>.</p>")
    body = (
        "<h2>ما تحتاجه</h2><ul><li><b>هاتف أندرويد</b> (الإصدار 8.0 أو أحدث) مع إنترنت.</li>"
        "<li><b>رقم الموظف</b> (أو البريد الوظيفي) و<b>كلمة المرور المؤقتة</b> من الموارد البشرية.</li>"
        "<li>تشغيل <b>الموقع (GPS)</b>.</li><li>أن تكون <b>في مقر عملك</b> عند تسجيل الحضور.</li></ul>"
        "<h2>التثبيت</h2><p>افتح <b>Google Play</b> وابحث عن <b>Raya Attendance</b> ثم اضغط <b>Install</b>. "
        "(خلال فترة الاختبار قد ترسل لك الموارد البشرية رابط دعوة بدلًا من ذلك.)</p>" + routine +
        "<h2>شرح الاستخدام خطوة بخطوة</h2>" + steps +
        "<h2>إذا حدثت مشكلة</h2>" + trouble +
        "<h2>خصوصيتك وعدالة النظام</h2>" + privacy +
        "<h2>للمديرين والموارد البشرية</h2>" + managers +
        "<div class='footer'>تحتاج مساعدة؟ تواصل مع قسم الموارد البشرية في رايا. يصف هذا الدليل الإصدار 1.0 من التطبيق. "
        "ملاحظة: نصوص التطبيق نفسها بالإنجليزية، لذلك تظهر أسماء الأزرار والرسائل بالإنجليزية داخل الشرح العربي.</div>")
    return page("ar", "Raya Attendance — دليل المستخدم وشرح الاستخدام", "للموظفين · تطبيق أندرويد · الإصدار 1.0", body)


# =============================================================================================
# 2. APP OPTIONS
# =============================================================================================


def home_map(callouts: list[tuple[int, float, float]]) -> str:
    marks = "".join(f"<i style='left:{x}%;top:{y}%'>{n}</i>" for n, x, y in callouts)
    return f"<div class='map'><img src='{img('home.png')}'>{marks}</div>"


HOME_MARKS = [(1, 79.5, 8.2), (2, 91.5, 8.2), (3, 1, 11), (4, 1, 31), (5, 1, 40), (6, 1, 58), (7, 1, 70), (8, 1, 82)]


def options_en() -> str:
    legend = table(["#", "Element", "What it shows / does"], [
        ["1", "Calendar icon", f"Opens {ui('My attendance')} (your history)."],
        ["2", "Three dots ⋮", f"{ui('Change password')} and {ui('Log out')}."],
        ["3", "Profile card", "Your name, employee ID, department, <b>Manager</b>, and your <b>Location</b> (main office). If you have several offices: “Also: …”. "
              + msg("None assigned - contact HR") + " means HR has not assigned an office yet."],
        ["4", "Date and clock", "Today's date and the current time."],
        ["5", "Today's status", "A coloured status (see the table below), then the day type: " + msg("Working hours 09:00 – 18:00") + ", "
              + msg("Holiday: …") + ", " + msg("You are on leave today") + " or " + msg("Not a working day") + ". After a check-in: "
              "<b>First check-in</b> time and <b>Worked</b> time."],
        ["6", "Location status", "A reminder: your location is checked by the server only at the moment you check in or out."],
        ["7", "Phone notice", f"Shown only when needed: {msg('This phone is waiting for HR approval…')} (button {ui('Check again')}) or "
              f"{msg('This phone couldn’t be registered.')} (button {ui('Try again')}), or {msg('This phone can’t be used for attendance. Please contact HR.')} "
              f"(the phone was rejected or switched off by HR)."],
        ["8", "CHECK IN / CHECK OUT", "The main button. It shows the next possible action: <b>CHECK IN</b> is green, <b>CHECK OUT</b> is red. "
              "It is <b>grey</b> while this phone is not approved by HR. If your office uses a QR code, a line under the button says "
              + msg("You will scan the QR code on the office screen.")],
    ])
    status = table(["Status", "Meaning"], [
        [chip("n", "Not checked in"), "No check-in yet today."],
        [chip("g", "Checked in"), "You are checked in, on time."],
        [chip("a", "Checked in · Late"), "You checked in after the start time plus the grace period set by HR (usually 15 minutes)."],
        [chip("p", "Checked in · Pending review"), "Recorded; HR is reviewing the check-in."],
        [chip("b", "Checked out"), "You checked out. Hours worked are shown."],
        [chip("a", "Checked out · Late"), "Checked out; you had arrived late."],
        [chip("p", "Pending review"), "The day is waiting for HR's decision."],
        [chip("g", "Present"), "(History) Present on time."],
        [chip("a", "Late"), "(History) Present but late."],
        [chip("r", "Absent"), "(History) Working day with no valid attendance."],
        [chip("n", "Holiday"), "Public or company holiday. Not counted as absence."],
        [chip("n", "On leave"), "Approved leave. Not counted as absence."],
        [chip("n", "Day off"), "Not a working day for you (for example Sunday)."],
    ])
    results = table(["Result card / attempt", "Meaning"], [
        [chip("g", "Checked in") + " / " + chip("b", "Checked out"), msg("Check-in successful.") + " / " + msg("Check-out successful.") + " With time, office and distance from the office point."],
        [chip("p", "Recorded – pending review"), msg("Your attendance was recorded and is waiting for HR review.")],
        [chip("r", "Not accepted"), "The attempt was refused. The card explains why (for example outside the office area, weak signal, or contact HR). "
                                    "The home screen then shows " + msg("Last attempt was not accepted") + "."],
        [msg("Not completed"), "A pop-up when the attempt could not be completed (for example no internet)."],
    ])
    perms = table(["Permission", "Why", "When"], [
        ["Location (precise)", "To confirm you are at your workplace.", "Only at the moment you tap CHECK IN / CHECK OUT. Choose “While using the app”."],
        ["Camera", "To read the office QR code.", "Only if your office requires the QR code."],
        ["Internet", "To send the check-in to Raya's server.", "During check-in, reports and login."],
    ])
    reports = (f"<p>Only <b>managers, HR and admins</b> see the chart icon. Employees do not.</p>"
               + table(["Tab / option", "What it does"], [
                   [ui("Create a report"), "Choose the <b>report</b>, the <b>date</b> (or month, or date range), the format <b>Excel</b> or <b>PDF</b>, then tap "
                    f"{ui('DOWNLOAD')}. The file is saved in <b>Downloads/Attendance</b>; tap {ui('OPEN')} to view it."],
                   ["Report types", "Daily report · Weekly report · Monthly report · Attendance summary (dates) · Late arrivals · Absences · Suspicious attendance."],
                   [ui("Ready reports"), "Reports created automatically by HR's schedules (for example every Monday). Tap one to download it. Pull down to refresh. "
                    "Files are kept for a limited time (90 days by default)."],
                   ["Who sees what", "<b>Managers</b>: only their own team. <b>HR</b>: all employees."],
               ]) + f"<div style='display:flex;gap:14px;margin-top:8px'>{fig('reports-create.png', 'Create a report')}{fig('reports-ready.png', 'Ready reports')}</div>")
    rules = ("<ul><li><b>One phone per employee</b>, approved by HR.</li><li><b>No offline check-in</b>: the phone needs internet.</li>"
             "<li><b>The server's clock decides</b>, not the phone's clock.</li><li>5 wrong passwords lock the login for 15 minutes.</li>"
             "<li>Passwords: at least 10 characters, different from the current one, not containing your name, ID or email name.</li>"
             "<li>Location is read only at check-in / check-out; no background tracking.</li></ul>")
    body = (
        "<h2>1. Screens at a glance</h2>"
        + table(["Screen", "How to open it"], [
            [ui("Login"), "Shown when you are logged out."],
            [ui("Change password"), f"First login (automatic), or ⋮ menu → {ui('Change password')}."],
            [ui("Home (Attendance)"), "The main screen after login."],
            [ui("My attendance"), "Calendar icon on Home."],
            [ui("Scan the office QR code"), "Opens by itself during check-in if your office requires it."],
            [ui("Reports"), "Chart icon on Home (managers, HR, admins only)."],
        ])
        + "<h2>2. The Home screen</h2><div class='step'>" + home_map(HOME_MARKS) + f"<div class='text'>{legend}</div></div>"
        + "<h2 class='pb'>3. Status labels</h2>" + status
        + "<h2>4. Results and messages after a check-in</h2>" + results
        + "<h2>5. Other screens</h2>"
        + "<h3>Login</h3><p>Fields: <b>Employee ID or email</b>, <b>Password</b> (eye icon to show). Button " + ui("LOG IN") + ". Text: “Forgot your password? Ask HR to reset it.”</p>"
        + "<h3>My attendance</h3><p>Arrows ‹ › change the month (you cannot go past the current month). The summary card shows <b>Present</b>, <b>Late</b> and <b>Worked</b>; "
          "each day shows date, first check-in – last check-out, hours, office and a status chip.</p>"
        + "<h3>Change password</h3><p>Fields: current (or temporary) password, <b>New password</b>, <b>Repeat new password</b>. Button " + ui("SAVE PASSWORD") + ". Errors: "
          + msg("At least 10 characters") + ", " + msg("Must be different from the current password") + ", " + msg("The passwords are not the same") + ".</p>"
        + "<h3>Scan the office QR code</h3><p>Point the camera at the QR screen in the office. It changes every 30 seconds, so scan it when you are there; "
          "a photo or a forwarded picture of the code does not work.</p>"
        + "<h2>6. Permissions</h2>" + perms
        + "<h2 class='pb'>7. Reports (managers and HR)</h2>" + reports
        + "<h2>8. Rules to remember</h2>" + rules
        + "<div class='footer'>This reference describes version 1.0 of the Raya Attendance app. Questions: Raya HR department.</div>")
    return page("en", "Raya Attendance — App Options", "Every screen, button, status and message · Version 1.0", body)


def options_ar() -> str:
    legend = table(["#", "العنصر", "ماذا يعرض / ماذا يفعل"], [
        ["1", "أيقونة التقويم", f"تفتح {ui('My attendance')} (سجل حضورك)."],
        ["2", "النقاط الثلاث ⋮", f"{ui('Change password')} و{ui('Log out')}."],
        ["3", "بطاقة الملف الشخصي", "اسمك ورقم الموظف والقسم و<b>Manager</b> (المدير) و<b>Location</b> (مقر عملك الرئيسي). إذا كان لديك عدة مكاتب: «Also: …». "
              + msg("None assigned - contact HR") + " تعني أن الموارد البشرية لم تعيّن لك مكتبًا بعد."],
        ["4", "التاريخ والساعة", "تاريخ اليوم والوقت الحالي."],
        ["5", "Today's status (حالة اليوم)", "حالة ملوّنة (انظر الجدول أدناه) ثم نوع اليوم: " + msg("Working hours 09:00 – 18:00") + " أو "
              + msg("Holiday: …") + " أو " + msg("You are on leave today") + " أو " + msg("Not a working day") + ". بعد تسجيل الحضور: "
              "وقت <b>First check-in</b> والوقت <b>Worked</b>."],
        ["6", "Location status", "تذكير: يُفحص موقعك بواسطة الخادم فقط لحظة تسجيل الحضور أو الانصراف."],
        ["7", "إشعار الهاتف", f"يظهر عند الحاجة فقط: {msg('This phone is waiting for HR approval…')} (الزر {ui('Check again')}) أو "
              f"{msg('This phone couldn’t be registered.')} (الزر {ui('Try again')}) أو {msg('This phone can’t be used for attendance. Please contact HR.')} "
              f"(رفضت الموارد البشرية الهاتف أو أوقفته)."],
        ["8", "CHECK IN / CHECK OUT", "الزر الرئيسي. يعرض الإجراء التالي الممكن: <b>CHECK IN</b> أخضر و<b>CHECK OUT</b> أحمر. "
              "ويكون <b>رماديًا</b> ما دام هذا الهاتف غير معتمد من الموارد البشرية. إذا كان مكتبك يستخدم رمز QR يظهر سطر تحت الزر: "
              + msg("You will scan the QR code on the office screen.")],
    ])
    status = table(["الحالة", "المعنى"], [
        [chip("n", "Not checked in"), "لم تسجّل حضورًا اليوم بعد."],
        [chip("g", "Checked in"), "أنت مسجَّل الحضور في الوقت المحدد."],
        [chip("a", "Checked in · Late"), "سجّلت الحضور بعد وقت البدء مضافًا إليه فترة السماح التي تحددها الموارد البشرية (عادة 15 دقيقة)."],
        [chip("p", "Checked in · Pending review"), "مسجَّل، والموارد البشرية تراجع تسجيل الحضور."],
        [chip("b", "Checked out"), "سجّلت الانصراف. تظهر الساعات المعمولة."],
        [chip("a", "Checked out · Late"), "سجّلت الانصراف، وكنت قد وصلت متأخرًا."],
        [chip("p", "Pending review"), "اليوم في انتظار قرار الموارد البشرية."],
        [chip("g", "Present"), "(في السجل) حاضر في الوقت."],
        [chip("a", "Late"), "(في السجل) حاضر لكن متأخر."],
        [chip("r", "Absent"), "(في السجل) يوم عمل دون حضور صالح."],
        [chip("n", "Holiday"), "عطلة رسمية أو عطلة الشركة. لا تُحتسب غيابًا."],
        [chip("n", "On leave"), "إجازة معتمدة. لا تُحتسب غيابًا."],
        [chip("n", "Day off"), "ليس يوم عمل بالنسبة لك (مثل يوم الأحد)."],
    ])
    results = table(["بطاقة النتيجة / المحاولة", "المعنى"], [
        [chip("g", "Checked in") + " / " + chip("b", "Checked out"), msg("Check-in successful.") + " / " + msg("Check-out successful.") + " مع الوقت والمكتب والمسافة من نقطة المكتب."],
        [chip("p", "Recorded – pending review"), msg("Your attendance was recorded and is waiting for HR review.") + " (مسجَّل وتراجعه الموارد البشرية)."],
        [chip("r", "Not accepted"), "رُفضت المحاولة. تشرح البطاقة السبب (مثل خارج نطاق المكتب أو ضعف الإشارة أو التواصل مع الموارد البشرية). "
                                    "ثم تعرض الشاشة الرئيسية " + msg("Last attempt was not accepted") + "."],
        [msg("Not completed"), "نافذة منبثقة عند تعذّر إتمام المحاولة (مثل عدم وجود إنترنت)."],
    ])
    perms = table(["الإذن", "السبب", "متى"], [
        ["الموقع (دقيق)", "للتأكد من وجودك في مقر عملك.", "فقط لحظة الضغط على CHECK IN / CHECK OUT. اختر «أثناء استخدام التطبيق»."],
        ["الكاميرا", "لقراءة رمز QR الخاص بالمكتب.", "فقط إذا كان مكتبك يتطلب رمز QR."],
        ["الإنترنت", "لإرسال تسجيل الحضور إلى خادم رايا.", "أثناء تسجيل الحضور والتقارير وتسجيل الدخول."],
    ])
    reports = (f"<p>يرى <b>المديرون والموارد البشرية والمسؤولون</b> فقط أيقونة المخطط. الموظفون لا يرونها.</p>"
               + table(["التبويب / الخيار", "ماذا يفعل"], [
                   [ui("Create a report"), "اختر <b>التقرير</b> و<b>التاريخ</b> (أو الشهر أو الفترة) والصيغة <b>Excel</b> أو <b>PDF</b> ثم اضغط "
                    f"{ui('DOWNLOAD')}. يُحفظ الملف في <b>Downloads/Attendance</b>؛ اضغط {ui('OPEN')} لعرضه."],
                   ["أنواع التقارير", "<ul><li>" + ui("Daily report") + " — يومي</li><li>" + ui("Weekly report") + " — أسبوعي</li><li>" + ui("Monthly report") + " — شهري</li><li>"
                    + ui("Attendance summary (dates)") + " — ملخص لفترة تحددها</li><li>" + ui("Late arrivals") + " — حالات التأخير</li><li>" + ui("Absences") + " — الغياب</li><li>"
                    + ui("Suspicious attendance") + " — حضور مشبوه</li></ul>"],
                   [ui("Ready reports"), "تقارير تنشئها جداول الموارد البشرية تلقائيًا (مثل كل يوم اثنين). اضغط تقريرًا لتنزيله. اسحب للأسفل للتحديث. "
                    "تُحفظ الملفات مدة محدودة (90 يومًا افتراضيًا)."],
                   ["من يرى ماذا", "<b>المديرون</b>: فريقهم فقط. <b>الموارد البشرية</b>: جميع الموظفين."],
               ]) + f"<div style='display:flex;gap:14px;margin-top:8px'>{fig('reports-create.png', 'Create a report')}{fig('reports-ready.png', 'Ready reports')}</div>")
    rules = ("<ul><li><b>هاتف واحد لكل موظف</b>، تعتمده الموارد البشرية.</li><li><b>لا تسجيل حضور دون اتصال</b>: يحتاج الهاتف إلى إنترنت.</li>"
             "<li><b>ساعة الخادم هي المعتمدة</b> وليست ساعة الهاتف.</li><li>5 كلمات مرور خاطئة تقفل الدخول 15 دقيقة.</li>"
             "<li>كلمة المرور: 10 أحرف على الأقل، مختلفة عن الحالية، ولا تحتوي على اسمك أو رقمك أو جزء من بريدك.</li>"
             "<li>يُقرأ الموقع فقط عند الحضور/الانصراف؛ لا تتبّع في الخلفية.</li></ul>")
    body = (
        "<h2>1. الشاشات في نظرة سريعة</h2>"
        + table(["الشاشة", "كيف تفتحها"], [
            [ui("Login"), "تظهر عندما تكون مسجّلًا للخروج."],
            [ui("Change password"), f"عند أول دخول (تلقائيًا)، أو من قائمة ⋮ ← {ui('Change password')}."],
            [ui("Home (Attendance)"), "الشاشة الرئيسية بعد تسجيل الدخول."],
            [ui("My attendance"), "أيقونة التقويم في الشاشة الرئيسية."],
            [ui("Scan the office QR code"), "تُفتح تلقائيًا أثناء تسجيل الحضور إذا كان مكتبك يتطلب ذلك."],
            [ui("Reports"), "أيقونة المخطط في الشاشة الرئيسية (للمديرين والموارد البشرية والمسؤولين فقط)."],
        ])
        + "<h2>2. الشاشة الرئيسية</h2><div class='step'>" + home_map(HOME_MARKS) + f"<div class='text'>{legend}</div></div>"
        + "<h2 class='pb'>3. تسميات الحالة</h2>" + status
        + "<h2>4. النتائج والرسائل بعد تسجيل الحضور</h2>" + results
        + "<h2>5. شاشات أخرى</h2>"
        + "<h3>تسجيل الدخول</h3><p>الحقول: " + ui("Employee ID or email") + " (رقم الموظف أو البريد) و" + ui("Password") + " (كلمة المرور؛ أيقونة العين للإظهار). الزر " + ui("LOG IN") + ". النص أسفل الزر: " + msg("Forgot your password? Ask HR to reset it.") + " أي: نسيت كلمة المرور؟ اطلب من الموارد البشرية إعادة تعيينها.</p>"
        + "<h3>حضوري (" + ui("My attendance") + ")</h3><p>الأسهم ‹ › لتغيير الشهر (لا يمكن تجاوز الشهر الحالي). تعرض بطاقة الملخص عدد أيام " + ui("Present") + " (حاضر) و" + ui("Late") + " (متأخر) ومجموع " + ui("Worked") + " (الساعات المعمولة)؛ "
          "وكل يوم يعرض التاريخ وأول حضور – آخر انصراف والساعات والمكتب وحالة ملوّنة.</p>"
        + "<h3>تغيير كلمة المرور</h3><p>الحقول: " + ui("Current password") + " (كلمة المرور الحالية، أو المؤقتة عند أول دخول) و" + ui("New password") + " (الجديدة) و" + ui("Repeat new password") + " (تكرار الجديدة). الزر " + ui("SAVE PASSWORD") + ". رسائل الخطأ: "
          + msg("At least 10 characters") + " (10 أحرف على الأقل) و" + msg("Must be different from the current password") + " (يجب أن تختلف عن الحالية) و" + msg("The passwords are not the same") + " (كلمتا المرور غير متطابقتين).</p>"
        + "<h3>مسح رمز QR الخاص بالمكتب</h3><p>وجّه الكاميرا نحو شاشة QR في المكتب. يتغيّر الرمز كل 30 ثانية لذلك امسحه وأنت هناك؛ "
          "لا تنفع صورة للرمز أو صورة مُرسَلة.</p>"
        + "<h2>6. الأذونات</h2>" + perms
        + "<h2 class='pb'>7. التقارير (للمديرين والموارد البشرية)</h2>" + reports
        + "<h2>8. قواعد يجب تذكّرها</h2>" + rules
        + "<div class='footer'>يصف هذا المرجع الإصدار 1.0 من تطبيق Raya Attendance. للاستفسار: قسم الموارد البشرية في رايا. "
        "نصوص التطبيق نفسها بالإنجليزية، لذلك تظهر أسماء الأزرار والرسائل بالإنجليزية داخل الشرح العربي.</div>")
    return page("ar", "Raya Attendance — خيارات التطبيق", "كل شاشة وزر وحالة ورسالة · الإصدار 1.0", body)


def render(html: str, name: str) -> None:
    src = HERE / f"{name}.html"
    src.write_text(html, encoding="utf-8")
    pdf = HERE / f"{name}.pdf"
    subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf}", src.as_uri()],
                   check=True, capture_output=True, timeout=120)
    src.unlink()
    print(pdf.name, f"{pdf.stat().st_size // 1024} KB")


def main() -> None:
    render(walkthrough_en(), "Raya-Attendance-User-Guide-EN")
    render(walkthrough_ar(), "Raya-Attendance-User-Guide-AR")
    render(options_en(), "Raya-Attendance-App-Options-EN")
    render(options_ar(), "Raya-Attendance-App-Options-AR")


if __name__ == "__main__":
    main()
