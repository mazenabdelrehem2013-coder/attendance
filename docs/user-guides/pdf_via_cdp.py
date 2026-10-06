"""Turns an HTML guide into an A4 PDF without the browser's print engine.

Chrome/Edge on this PC answer "Printing is not available" (2026-10-07), so the page is laid out on screen at A4
width, blocks that would be cut by a page end are pushed to the next page (and class 'pb' starts a new page),
each page is photographed at 2x, and Pillow joins the pictures into a PDF (text is not selectable).
    pdf_via_cdp.print_pdf(html_path, pdf_path)
"""

import asyncio
import base64
import io
import json
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets
from PIL import Image

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BROWSER = CHROME if Path(CHROME).exists() else EDGE
PORT = 9341
SCALE = 2
# A4 at 96 dpi = 794 x 1123 px; margins 13 mm sides, 14 mm top, 16 mm bottom.
PAGE_W, PAGE_H, SIDE, TOP, BOTTOM = 794, 1123, 49, 53, 60
CONTENT_H = PAGE_H - TOP - BOTTOM

PAGINATE = """(() => {
  const H = %d;
  document.body.style.margin = '0'; document.body.style.padding = '0 %dpx';
  const top = el => el.getBoundingClientRect().top + window.scrollY;
  const push = (el, delta) => {
    if (delta <= 0) return;
    if (el.tagName === 'TR') {
      const spacer = document.createElement('tr');
      spacer.innerHTML = `<td colspan="99" style="border:none;padding:0;height:${delta}px"></td>`;
      el.parentNode.insertBefore(spacer, el);
    } else {
      // a spacer block (a bigger margin would collapse with the previous element's margin)
      const spacer = document.createElement('div');
      el.parentNode.insertBefore(spacer, el);
      const t2 = top(el);
      spacer.style.height = Math.max(0, Math.ceil(t2 / H) * H - t2) + 'px';
    }
  };
  const atoms = [...document.body.querySelectorAll(
    'h2, h3, p, li, tr, figure, .box, .tip, .warn, .cover, .step, .footer, .half')];
  for (const el of atoms) {
    if (el.closest('.box, .tip, .warn, .step, figure, .half') && !el.matches('.box, .tip, .warn, .step, figure, .half')) continue;
    const t = top(el), h = el.getBoundingClientRect().height, page = Math.floor(t / H);
    const end = (page + 1) * H;
    if (el.classList.contains('pb') && t %% H > 2) { push(el, end - t); continue; }
    if (h <= H && t + h > end) { push(el, end - t); continue; }
    if (el.matches('h2, h3') && end - (t + h) < 90) push(el, end - t);  // keep headings with what follows
  }
  return Math.ceil(document.documentElement.scrollHeight / H);
})()"""


async def _print(html: Path, pdf: Path, png_dir: Path | None = None) -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        proc = subprocess.Popen([BROWSER, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                                 f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}", "about:blank"])
        try:
            for _ in range(60):
                try:
                    tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
                    ws_url = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page")
                    break
                except Exception:
                    time.sleep(0.5)
            async with websockets.connect(ws_url, max_size=500_000_000) as ws:
                n = 0

                async def cdp(method, **params):
                    nonlocal n
                    n += 1
                    my = n
                    await ws.send(json.dumps({"id": my, "method": method, "params": params}))
                    while True:
                        msg = json.loads(await ws.recv())
                        if msg.get("id") == my:
                            if "error" in msg:
                                raise RuntimeError(f"{method}: {msg['error']}")
                            return msg.get("result", {})

                await cdp("Page.enable")
                await cdp("Emulation.setDeviceMetricsOverride", width=PAGE_W, height=PAGE_H, deviceScaleFactor=SCALE, mobile=False)
                await cdp("Emulation.setEmulatedMedia", media="print")
                await cdp("Page.navigate", url=html.resolve().as_uri())
                await asyncio.sleep(3)  # images and fonts
                r = await cdp("Runtime.evaluate", expression=PAGINATE % (CONTENT_H, SIDE), returnByValue=True)
                pages = int(r["result"]["value"])
                await asyncio.sleep(1)
                images = []
                for k in range(pages):
                    await cdp("Page.bringToFront")
                    shot = await cdp("Page.captureScreenshot", format="png", captureBeyondViewport=True, fromSurface=True,
                                     clip={"x": 0, "y": k * CONTENT_H, "width": PAGE_W, "height": CONTENT_H, "scale": 1})
                    body = Image.open(io.BytesIO(base64.b64decode(shot["data"]))).convert("RGB")
                    page = Image.new("RGB", (PAGE_W * SCALE, PAGE_H * SCALE), "white")
                    page.paste(body, (0, TOP * SCALE))
                    images.append(page)
                    if png_dir:  # page previews for proofreading
                        png_dir.mkdir(parents=True, exist_ok=True)
                        page.resize((PAGE_W, PAGE_H)).save(png_dir / f"{pdf.stem}-p{k + 1}.png")
                images[0].save(pdf, save_all=True, append_images=images[1:], resolution=96 * SCALE)
        finally:
            proc.terminate()
            proc.wait(timeout=30)


def _print_cli(html: Path, pdf: Path) -> bool:
    """Edge's own print-to-PDF (real, selectable text). It needs its OWN profile folder: with the default one
    it hands the job to an Edge window that is already open and nothing is written. The launcher returns
    before the file is written, so wait for it."""
    pdf.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={profile}",
                        f"--print-to-pdf={pdf}", html.resolve().as_uri()], capture_output=True, timeout=120)
        last = -1
        for _ in range(120):
            size = pdf.stat().st_size if pdf.exists() else -1
            if size > 0 and size == last:
                return True
            last = size
            time.sleep(1)
    return False


def print_pdf(html: Path, pdf: Path) -> None:
    if not _print_cli(html, pdf):
        asyncio.run(_print(html, pdf))  # fallback: page pictures
