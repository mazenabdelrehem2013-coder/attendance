r"""Creates the Google Play store images from HTML templates, photographed by Microsoft Edge
(headless). Run from anywhere:   backend\.venv\Scripts\python mobile\store\make_store_images.py

Output (mobile/store/out): icon-512.png, feature-1024x500.png, screenshot-1..4.png (1080x1920).
"""

import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
SHOTS = HERE.parents[1] / "docs" / "screenshots"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
BLUE = "#1F5FAD"

# Material "fingerprint" icon (Apache License 2.0) - the same symbol as the app and dashboard.
FINGERPRINT = (
    "M17.81 4.47c-.08 0-.16-.02-.23-.06C15.66 3.42 14 3 12.01 3c-1.98 0-3.86.47-5.57 1.41-.24.13-.54.04-.68-.2-.13-.24-.04-.55.2-.68C7.82 2.52 9.86 2 12.01 2c2.13 0 3.99.47 6.03 1.52.25.13.34.43.21.67-.09.18-.26.28-.44.28M3.5 9.72c-.1 0-.2-.03-.29-.09-.23-.16-.28-.47-.12-.7.99-1.4 2.25-2.5 3.75-3.27C9.98 4.04 14 4.03 17.15 5.65c1.5.77 2.76 1.86 3.75 3.25.16.22.11.54-.12.7s-.54.11-.7-.12c-.9-1.26-2.04-2.25-3.39-2.94-2.87-1.47-6.54-1.47-9.4.01-1.36.7-2.5 1.7-3.4 2.96-.08.14-.23.21-.39.21m6.25 12.07c-.13 0-.26-.05-.35-.15-.87-.87-1.34-1.43-2.01-2.64-.69-1.23-1.05-2.73-1.05-4.34 0-2.97 2.54-5.39 5.66-5.39s5.66 2.42 5.66 5.39c0 .28-.22.5-.5.5s-.5-.22-.5-.5c0-2.42-2.09-4.39-4.66-4.39s-4.66 1.97-4.66 4.39c0 1.44.32 2.77.93 3.85.64 1.15 1.08 1.64 1.85 2.42.19.2.19.51 0 .71-.11.1-.24.15-.37.15m7.17-1.85c-1.19 0-2.24-.3-3.1-.89-1.49-1.01-2.38-2.65-2.38-4.39 0-.28.22-.5.5-.5s.5.22.5.5c0 1.41.72 2.74 1.94 3.56.71.48 1.54.71 2.54.71.24 0 .64-.03 1.04-.1.27-.05.53.13.58.41.05.27-.13.53-.41.58-.57.11-1.07.12-1.21.12M14.91 22c-.04 0-.09-.01-.13-.02-1.59-.44-2.63-1.03-3.72-2.1-1.4-1.39-2.17-3.24-2.17-5.22 0-1.62 1.38-2.94 3.08-2.94s3.08 1.32 3.08 2.94c0 1.07.93 1.94 2.08 1.94s2.08-.87 2.08-1.94c0-3.77-3.25-6.83-7.25-6.83-2.84 0-5.44 1.58-6.61 4.03-.39.81-.59 1.76-.59 2.8 0 .78.07 2.01.67 3.61.1.26-.03.55-.29.64-.26.1-.55-.04-.64-.29-.49-1.31-.73-2.61-.73-3.96 0-1.2.23-2.29.68-3.24 1.33-2.79 4.28-4.6 7.51-4.6 4.55 0 8.25 3.51 8.25 7.83 0 1.62-1.38 2.94-3.08 2.94s-3.08-1.32-3.08-2.94c0-1.07-.93-1.94-2.08-1.94s-2.08.87-2.08 1.94c0 1.71.66 3.31 1.87 4.51.95.94 1.86 1.46 3.27 1.85.27.07.42.35.35.61-.05.23-.26.38-.47.38"
)
BASE = "<!doctype html><html><head><meta charset='utf-8'><style>html,body{margin:0;overflow:hidden;font-family:'Segoe UI',Roboto,Arial,sans-serif}</style></head><body>{}</body></html>"


def icon_svg(size: int, fg: str = "#fff") -> str:
    return f"<svg width='{size}' height='{size}' viewBox='0 0 24 24'><path fill='{fg}' d='{FINGERPRINT}'/></svg>"


ICON = BASE.replace("{}", f"<div style='width:512px;height:512px;background:{BLUE};display:flex;align-items:center;justify-content:center'>{icon_svg(300)}</div>")

FEATURE = BASE.replace("{}", f"""
<div style='width:1024px;height:500px;background:linear-gradient(135deg,{BLUE},#0f3d75);color:#fff;display:flex;align-items:center;padding:0 70px;box-sizing:border-box;gap:56px'>
  <div style='flex:none;width:220px;height:220px;border-radius:48px;background:rgba(255,255,255,.12);display:flex;align-items:center;justify-content:center'>{icon_svg(150)}</div>
  <div>
    <div style='font-size:64px;font-weight:700;line-height:1.05'>Raya Attendance</div>
    <div style='font-size:30px;margin-top:18px;opacity:.92;line-height:1.3'>Check in at your workplace in one tap.<br>Secure, private, verified.</div>
  </div>
</div>""")

SCREENSHOTS = [  # emulator captures (1080x2400) from the local demo data
    ("store-checked-in.png", "Check in with one tap"),
    ("store-home-in.png", "Your day at a glance"),
    ("store-history.png", "Your monthly attendance"),
    ("store-reports-create.png", "Managers: download team reports"),
    ("store-reports-ready.png", "Reports ready every morning"),
]


def screenshot_html(image: Path, caption: str) -> str:
    # The phone image is shown 6 px larger than its frame, so the emulator's thin coloured edge is cut off.
    return BASE.replace("{}", f"""
<div style='width:1080px;height:1920px;background:linear-gradient(180deg,{BLUE} 0%,#0f3d75 100%);display:flex;flex-direction:column;align-items:center'>
  <div style='color:#fff;font-size:64px;font-weight:700;text-align:center;padding:110px 60px 70px;line-height:1.15'>{caption}</div>
  <div style='width:648px;height:1440px;border-radius:44px;overflow:hidden;box-shadow:0 24px 60px rgba(0,0,0,.35)'>
    <img src='{image.as_uri()}' style='width:660px;height:1467px;margin:-6px 0 0 -6px;display:block'>
  </div>
</div>""")


def shoot(html: str, name: str, width: int, height: int) -> None:
    page = OUT / f"{name}.html"
    page.write_text(html, encoding="utf-8")
    png = OUT / f"{name}.png"
    subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                    f"--window-size={width},{height}", f"--screenshot={png}", page.as_uri()],
                   check=True, capture_output=True, timeout=60)
    page.unlink()
    print(f"{png.name}  {width}x{height}")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    shoot(ICON, "icon-512", 512, 512)
    shoot(FEATURE, "feature-1024x500", 1024, 500)
    for i, (file, caption) in enumerate(SCREENSHOTS, 1):
        shoot(screenshot_html(SHOTS / file, caption), f"screenshot-{i}", 1080, 1920)


if __name__ == "__main__":
    main()
