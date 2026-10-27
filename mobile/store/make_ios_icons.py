r"""Creates the iOS app icons (ios/Runner/Assets.xcassets/AppIcon.appiconset) from the same
fingerprint symbol and blue as the Android icon and the Google Play icon.

    python mobile/store/make_ios_icons.py [path-to-chrome-or-edge]

Needs Pillow. Apple wants square, fully opaque PNGs (no transparency, no rounded corners -
iOS rounds them itself).
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

from make_store_images import BASE, BLUE, EDGE, icon_svg

HERE = Path(__file__).resolve().parent
ICONSET = HERE.parent / "ios" / "Runner" / "Assets.xcassets" / "AppIcon.appiconset"

# Same proportions as icon-512 (symbol = 300/512 of the side).
ICON_1024 = BASE.replace("{}", f"<div style='width:1024px;height:1024px;background:{BLUE};display:flex;align-items:center;justify-content:center'>{icon_svg(600)}</div>")


def render_1024(browser: str) -> Image.Image:
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "icon.html"
        png = Path(tmp) / "icon.png"
        page.write_text(ICON_1024, encoding="utf-8")
        subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-sandbox",
                        "--force-device-scale-factor=1", "--window-size=1024,1200",
                        f"--screenshot={png}", page.as_uri()],
                       check=True, capture_output=True, timeout=60)
        # The window is taller than the page: headless browsers keep part of it for their own frame.
        return Image.open(png).convert("RGB").crop((0, 0, 1024, 1024))


def main() -> None:
    master = render_1024(sys.argv[1] if len(sys.argv) > 1 else EDGE)
    contents = json.loads((ICONSET / "Contents.json").read_text(encoding="utf-8"))
    for entry in contents["images"]:
        side = round(float(entry["size"].split("x")[0]) * int(entry["scale"].rstrip("x")))
        master.resize((side, side), Image.LANCZOS).save(ICONSET / entry["filename"], optimize=True)
        print(f"{entry['filename']}  {side}x{side}")


if __name__ == "__main__":
    main()
