r"""Creates the Google Play publishing guide as PDF in English and Arabic (right-to-left),
with the icon, feature graphic and screenshots. Printed by Microsoft Edge (headless), which
handles Arabic text correctly.
    backend\.venv\Scripts\python mobile\store\make_store_pdfs.py
Output: mobile/store/out/Raya-Attendance-Google-Play-EN.pdf and ...-AR.pdf
"""

import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PRIVACY = "https://raya.34.35.174.159.nip.io/privacy.html"
EMAIL = "mazenabdelrehem2013@gmail.com"

EN = {
    "lang": "en", "dir": "ltr",
    "title": "Raya Attendance — Google Play publishing pack",
    "subtitle": "Store listing, graphics and step-by-step Play Console guide · Version 1.0.0 · October 2026",
    "facts_h": "Key facts",
    "facts": [
        ("App name", "Raya Attendance"),
        ("Package (permanent)", "com.raya.attendance"),
        ("Version", "1.0.0 (version code 1)"),
        ("File to upload", "app-release.aab (signed with the Raya upload key)"),
        ("Category", "Business"),
        ("Price", "Free · no ads · no in-app purchases"),
        ("Privacy policy", PRIVACY),
        ("Contact email", EMAIL),
        ("Reviewer login", "Employee ID PLAY-REVIEW (password: read it from the server, never written in documents)"),
    ],
    "listing_h": "Store listing texts",
    "short_l": "Short description (max 80 characters)",
    "short": "Check in and out at your Raya workplace in one tap – secure and verified.",
    "full_l": "Full description",
    "full": [
        "Raya Attendance is the official attendance app for employees of Raya.",
        "<b>Check in and out in one tap.</b> Arrive at your workplace, open the app and tap Check in. The app confirms you are at your assigned workplace and records the time. Tap Check out when you leave. Several check-ins per day are supported (for example lunch breaks).",
        "<b>See your day and your history.</b> Today's status, working hours, first check-in and hours worked are always visible. “My attendance” shows every day of the month: present, late, on leave or holiday.",
        "<b>For managers and HR.</b> Managers and HR can create attendance reports (daily, weekly, monthly, late arrivals, absences) and download them as Excel or PDF, or open reports that were prepared automatically.",
        "<b>Secure and fair.</b> Each employee's phone must be approved by HR, so one phone cannot be used for several people. Every check-in is signed by your approved phone and verified by the server. Unusual check-ins are reviewed by HR instead of being counted automatically.",
        "<b>Your privacy.</b> Your location is used only at the moment you tap Check in or Check out – never in the background and never to track you. The camera is used only to scan your office's QR screen, if your workplace uses one; no photos are taken or stored. No advertising and no third-party tracking.",
        "An account is required: it is created by Raya's HR department. If you can't log in, please contact HR.",
    ],
    "graphics_h": "Graphics",
    "icon_l": "App icon · 512 × 512 · icon-512.png",
    "feature_l": "Feature graphic · 1024 × 500 · feature-1024x500.png",
    "shots_l": "Phone screenshots · 1080 × 1920 · screenshot-1.png … screenshot-4.png",
    "steps_h": "Step by step in the Play Console",
    "steps": [
        ("Create the app", "play.google.com/console → <b>Create app</b> → name <b>Raya Attendance</b>, default language English, <b>App</b>, <b>Free</b>, accept the declarations."),
        ("Privacy policy", f"Policy → App content → Privacy policy → <b>{PRIVACY}</b>"),
        ("App access", "Choose <b>All or some functionality is restricted</b> → add login: username <b>PLAY-REVIEW</b> and its password. Note for reviewers: “Accounts are created by the employer (Raya HR). This review account has no workplace assigned, so it can log in and register a phone but cannot record attendance. New phones wait for HR approval by design.”"),
        ("Ads", "<b>No</b>, the app contains no ads."),
        ("Content rating", "Category <b>Utility, Productivity, Communication or other</b> → answer <b>No</b> to all content questions."),
        ("Target audience", "<b>18 and over</b>. News app: No. Government app: No. Financial features: None. Health: No."),
        ("Data safety", "Fill in as in the table below."),
        ("Store listing", "Grow → Store presence → Main store listing: paste the texts above, upload the icon, feature graphic and the 4 screenshots, category <b>Business</b>, contact email."),
        ("Closed testing", "Test and release → Testing → <b>Closed testing</b> → Create track (e.g. “Raya staff”) → Testers: at least <b>12</b> people → Create release → <b>accept Play App Signing</b> → upload <b>app-release.aab</b> → Review and roll out → share the opt-in link with the testers."),
        ("Play Integrity", "Test and release → App integrity → Play Integrity API → <b>Link a Cloud project</b> → <b>gen-lang-client-0101078644</b> (number 929211013841). Then ask for the check to be switched on on the server."),
        ("Going public", "If your developer account was created after 13 November 2023: after <b>14 days</b> of closed testing with 12+ testers → Dashboard → <b>Apply for production</b> → when approved, Production → Create release → roll out."),
    ],
    "safety_h": "Data safety answers",
    "safety_cols": ("Data", "Collected?", "Shared?", "Purpose"),
    "safety": [
        ("Precise location (only at check-in / check-out)", "Yes, required", "No", "App functionality; Fraud prevention, security"),
        ("Name, email address, user IDs, phone number (optional)", "Yes", "No", "App functionality; Account management"),
        ("App activity – other actions (check-in / check-out records)", "Yes", "No", "App functionality"),
        ("Device or other IDs", "Yes", "No", "Fraud prevention, security"),
        ("Photos, videos, contacts, messages, files, health, financial, audio, browsing", "No", "No", "—"),
    ],
    "safety_note": "Data is encrypted in transit: <b>Yes</b>. Users can request deletion: <b>Yes</b> (via the contact email). The camera only reads an office QR code; nothing is stored.",
    "keep_h": "Keep safe",
    "keep": "The upload key is in <b>D:\\claude\\keys</b> on the build PC. Back it up (USB stick or password manager). Never send it to anyone and never upload it to GitHub.",
}

AR = {
    "lang": "ar", "dir": "rtl",
    "title": "Raya Attendance — حزمة النشر على Google Play",
    "subtitle": "نصوص المتجر والصور ودليل Play Console خطوة بخطوة · الإصدار 1.0.0 · أكتوبر 2026",
    "facts_h": "معلومات أساسية",
    "facts": [
        ("اسم التطبيق", "Raya Attendance"),
        ("معرّف الحزمة (دائم ولا يتغيّر)", "com.raya.attendance"),
        ("الإصدار", "1.0.0 (رمز الإصدار 1)"),
        ("الملف المطلوب رفعه", "app-release.aab (موقَّع بمفتاح الرفع الخاص برايا)"),
        ("الفئة", "الأعمال (Business)"),
        ("السعر", "مجاني · بدون إعلانات · بدون مشتريات داخل التطبيق"),
        ("سياسة الخصوصية", PRIVACY),
        ("البريد الإلكتروني للتواصل", EMAIL),
        ("حساب المراجِع", "رقم الموظف PLAY-REVIEW (كلمة المرور تُقرأ من الخادم فقط، ولا تُكتب في أي مستند)"),
    ],
    "listing_h": "نصوص صفحة المتجر (يمكن إضافتها كترجمة عربية في Play Console)",
    "short_l": "الوصف المختصر (80 حرفًا كحدّ أقصى)",
    "short": "سجّل حضورك وانصرافك في مقر عملك في رايا بلمسة واحدة – بأمان وتحقّق.",
    "full_l": "الوصف الكامل",
    "full": [
        "Raya Attendance هو التطبيق الرسمي لتسجيل حضور موظفي رايا.",
        "<b>سجّل الحضور والانصراف بلمسة واحدة.</b> عند وصولك إلى مقر عملك افتح التطبيق واضغط «تسجيل الحضور»، فيتأكد التطبيق من وجودك في مقر عملك المحدَّد ويسجّل الوقت. واضغط «تسجيل الانصراف» عند المغادرة. يمكن التسجيل أكثر من مرة في اليوم (مثل استراحة الغداء).",
        "<b>تابع يومك وسجلّك.</b> حالة اليوم وساعات العمل وأول تسجيل حضور وعدد الساعات المعمولة تظهر دائمًا. وتعرض شاشة «حضوري» كل أيام الشهر: حاضر، متأخر، في إجازة أو عطلة رسمية.",
        "<b>للمديرين والموارد البشرية.</b> يمكن للمديرين وقسم الموارد البشرية إنشاء تقارير الحضور (يومية، أسبوعية، شهرية، التأخير، الغياب) وتنزيلها بصيغة Excel أو PDF، أو فتح التقارير المعدّة تلقائيًا.",
        "<b>آمن وعادل.</b> يجب أن يوافق قسم الموارد البشرية على هاتف كل موظف، فلا يمكن استخدام هاتف واحد لعدة أشخاص. كل تسجيل حضور موقَّع من هاتفك المعتمد ويتحقق منه الخادم. أما التسجيلات غير المعتادة فيراجعها قسم الموارد البشرية بدل احتسابها تلقائيًا.",
        "<b>خصوصيتك.</b> يُستخدم موقعك فقط لحظة الضغط على «تسجيل الحضور» أو «تسجيل الانصراف» – لا يُستخدم في الخلفية ولا لتتبّعك أبدًا. وتُستخدم الكاميرا فقط لمسح رمز QR الخاص بمكتبك إن كان مقر عملك يستخدمه، ولا تُلتقط أو تُحفظ أي صور. لا إعلانات ولا تتبّع من أطراف خارجية.",
        "يتطلّب التطبيق حسابًا يُنشئه قسم الموارد البشرية في رايا. إن لم تتمكن من تسجيل الدخول فتواصل مع الموارد البشرية.",
    ],
    "graphics_h": "الصور",
    "icon_l": "أيقونة التطبيق · 512 × 512 · icon-512.png",
    "feature_l": "صورة العرض الرئيسية · 1024 × 500 · feature-1024x500.png",
    "shots_l": "لقطات شاشة الهاتف · 1080 × 1920 · screenshot-1.png … screenshot-4.png",
    "steps_h": "الخطوات في Play Console",
    "steps": [
        ("إنشاء التطبيق", "play.google.com/console ← <b>Create app</b> ← الاسم <b>Raya Attendance</b>، اللغة الافتراضية English، اختر <b>App</b> ثم <b>Free</b>، ووافق على الإقرارات."),
        ("سياسة الخصوصية", f"Policy ← App content ← Privacy policy ← <b dir='ltr'>{PRIVACY}</b>"),
        ("الوصول إلى التطبيق (App access)", "اختر <b>All or some functionality is restricted</b> ← أضف بيانات الدخول: اسم المستخدم <b>PLAY-REVIEW</b> وكلمة المرور الخاصة به. ملاحظة للمراجعين (بالإنجليزية): “Accounts are created by the employer (Raya HR). This review account has no workplace assigned, so it can log in and register a phone but cannot record attendance. New phones wait for HR approval by design.”"),
        ("الإعلانات (Ads)", "<b>No</b> – التطبيق لا يحتوي على إعلانات."),
        ("تصنيف المحتوى", "الفئة <b>Utility, Productivity, Communication or other</b> ← أجب بـ <b>No</b> على كل أسئلة المحتوى."),
        ("الجمهور المستهدف", "<b>18 سنة فأكثر</b>. تطبيق أخبار: لا. تطبيق حكومي: لا. ميزات مالية: لا يوجد. صحة: لا."),
        ("أمان البيانات (Data safety)", "املأ النموذج كما في الجدول أدناه."),
        ("صفحة المتجر", "Grow ← Store presence ← Main store listing: الصق النصوص أعلاه، وارفع الأيقونة وصورة العرض و4 لقطات شاشة، الفئة <b>Business</b>، والبريد الإلكتروني للتواصل. لإضافة النص العربي: Manage translations ← Arabic."),
        ("الاختبار المغلق (Closed testing)", "Test and release ← Testing ← <b>Closed testing</b> ← Create track (مثل “Raya staff”) ← المختبِرون: <b>12</b> شخصًا على الأقل ← Create release ← <b>وافق على Play App Signing</b> ← ارفع <b>app-release.aab</b> ← Review and roll out ← أرسل رابط الاشتراك للمختبِرين."),
        ("Play Integrity", "Test and release ← App integrity ← Play Integrity API ← <b>Link a Cloud project</b> ← <b dir='ltr'>gen-lang-client-0101078644</b> (الرقم 929211013841). بعد ذلك اطلب تفعيل الفحص على الخادم."),
        ("النشر للعامة", "إذا أُنشئ حساب المطوّر بعد 13 نوفمبر 2023: بعد <b>14 يومًا</b> من الاختبار المغلق مع 12 مختبِرًا أو أكثر ← Dashboard ← <b>Apply for production</b> ← بعد الموافقة: Production ← Create release ← النشر."),
    ],
    "safety_h": "إجابات نموذج أمان البيانات (Data safety)",
    "safety_cols": ("البيانات", "تُجمع؟", "تُشارك؟", "الغرض"),
    "safety": [
        ("الموقع الدقيق (لحظة تسجيل الحضور/الانصراف فقط)", "نعم، إلزامي", "لا", "وظائف التطبيق؛ منع الاحتيال والأمان"),
        ("الاسم، البريد الإلكتروني، معرّفات المستخدم، رقم الهاتف (اختياري)", "نعم", "لا", "وظائف التطبيق؛ إدارة الحساب"),
        ("نشاط التطبيق – إجراءات أخرى (سجلات الحضور والانصراف)", "نعم", "لا", "وظائف التطبيق"),
        ("معرّفات الجهاز", "نعم", "لا", "منع الاحتيال والأمان"),
        ("الصور، الفيديو، جهات الاتصال، الرسائل، الملفات، الصحة، المال، الصوت، التصفح", "لا", "لا", "—"),
    ],
    "safety_note": "البيانات مشفّرة أثناء النقل: <b>نعم</b>. يمكن للمستخدم طلب حذف بياناته: <b>نعم</b> (عبر البريد الإلكتروني للتواصل). الكاميرا تقرأ رمز QR الخاص بالمكتب فقط ولا يُحفظ أي شيء.",
    "keep_h": "احتفظ بأمان",
    "keep": "مفتاح الرفع موجود في <b dir='ltr'>D:\\claude\\keys</b> على جهاز البناء. احتفظ بنسخة احتياطية منه (ذاكرة USB أو مدير كلمات المرور). لا ترسله لأي أحد ولا ترفعه إلى GitHub أبدًا.",
}


def html(t: dict) -> str:
    u = lambda name: (OUT / name).as_uri()  # noqa: E731
    facts = "".join(f"<tr><th>{k}</th><td dir='auto'>{v}</td></tr>" for k, v in t["facts"])
    full = "".join(f"<p>{p}</p>" for p in t["full"])
    steps = "".join(f"<li><b>{h}</b><br>{b}</li>" for h, b in t["steps"])
    cols = "".join(f"<th>{c}</th>" for c in t["safety_cols"])
    rows = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in t["safety"])
    shots = "".join(f"<img class='shot' src='{u(f'screenshot-{i}.png')}'>" for i in range(1, 5))
    return f"""<!doctype html><html lang='{t["lang"]}' dir='{t["dir"]}'><head><meta charset='utf-8'><style>
@page {{ size: A4; margin: 16mm 14mm; }}
body {{ font-family: 'Segoe UI', Tahoma, Arial, sans-serif; color: #1d2733; font-size: 10.5pt; line-height: 1.55; }}
h1 {{ color: #1F5FAD; font-size: 20pt; margin: 0 0 4px; }}
h2 {{ color: #1F5FAD; font-size: 13.5pt; border-bottom: 2px solid #1F5FAD; padding-bottom: 3px; margin-top: 22px; }}
.sub {{ color: #5f6b78; margin-bottom: 14px; }}
.cover {{ display: flex; gap: 18px; align-items: center; margin-bottom: 8px; }}
.cover img.icon {{ width: 86px; height: 86px; border-radius: 20px; }}
table {{ border-collapse: collapse; width: 100%; margin: 6px 0; }}
th, td {{ border: 1px solid #d5dbe3; padding: 5px 7px; vertical-align: top; text-align: start; }}
th {{ background: #eef3f9; width: 30%; }}
.safety th {{ width: auto; }}
.box {{ background: #f4f7fb; border: 1px solid #d5dbe3; border-radius: 6px; padding: 8px 12px; }}
.label {{ font-weight: 600; color: #5f6b78; margin-top: 10px; }}
ol li {{ margin-bottom: 8px; }}
.page {{ page-break-before: always; }}
.feature {{ width: 100%; border-radius: 8px; }}
.shots {{ display: flex; gap: 8px; justify-content: space-between; }}
.shot {{ width: 24%; border-radius: 8px; border: 1px solid #d5dbe3; }}
.warn {{ background: #fff4e5; border: 1px solid #f0c27b; border-radius: 6px; padding: 8px 12px; }}
</style></head><body>
<div class='cover'><img class='icon' src='{u("icon-512.png")}'><div><h1>{t["title"]}</h1><div class='sub'>{t["subtitle"]}</div></div></div>
<h2>{t["facts_h"]}</h2><table>{facts}</table>
<h2>{t["listing_h"]}</h2>
<div class='label'>{t["short_l"]}</div><div class='box'>{t["short"]}</div>
<div class='label'>{t["full_l"]}</div><div class='box'>{full}</div>
<div class='page'></div><h2>{t["graphics_h"]}</h2>
<div class='label'>{t["icon_l"]}</div><img src='{u("icon-512.png")}' style='width:120px;border-radius:24px'>
<div class='label'>{t["feature_l"]}</div><img class='feature' src='{u("feature-1024x500.png")}'>
<div class='label'>{t["shots_l"]}</div><div class='shots'>{shots}</div>
<div class='page'></div><h2>{t["steps_h"]}</h2><ol>{steps}</ol>
<h2>{t["safety_h"]}</h2><table class='safety'><tr>{cols}</tr>{rows}</table><p>{t["safety_note"]}</p>
<h2>{t["keep_h"]}</h2><div class='warn'>{t["keep"]}</div>
</body></html>"""


def main() -> None:
    for t, suffix in ((EN, "EN"), (AR, "AR")):
        page = OUT / f"guide-{suffix}.html"
        page.write_text(html(t), encoding="utf-8")
        pdf = OUT / f"Raya-Attendance-Google-Play-{suffix}.pdf"
        subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={pdf}", page.as_uri()], check=True, capture_output=True, timeout=90)
        page.unlink()
        print(pdf.name, f"{pdf.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
