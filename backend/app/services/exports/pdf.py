"""PDF reports (A4 landscape): company name, report title, period, generated date, summary,
detailed table (header repeated on every page) with totals, and page numbers."""

import io
import os
from datetime import date
from functools import lru_cache
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.exports.layout import Column, ReportDocument
from app.services.exports.layout import Table as LayoutTable

BRAND = colors.HexColor("#1F5FAD")
LIGHT = colors.HexColor("#E8EEF7")
GRID = colors.HexColor("#C9D3E3")

# Fonts covering all Latin letters used in Nigerian names (ẹ, ọ, ṣ, ń…): DejaVu on the server
# (installed in the Dockerfile), Arial/Segoe on Windows. Built-in Helvetica only as a last resort.
_FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
    (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"),
]


@lru_cache
def _fonts() -> tuple[str, str]:
    for regular, bold in _FONT_CANDIDATES:
        if os.path.exists(regular) and os.path.exists(bold):
            pdfmetrics.registerFont(TTFont("ReportFont", regular))
            pdfmetrics.registerFont(TTFont("ReportFont-Bold", bold))
            return "ReportFont", "ReportFont-Bold"
    return "Helvetica", "Helvetica-Bold"


def _text(value, kind: str) -> str:
    if value is None or value == "":
        return "—"
    if kind == "minutes":
        minutes = int(value)
        return f"{minutes // 60}h {minutes % 60:02d}m"
    if kind == "percent":
        return f"{float(value) * 100:.1f}%"
    if kind == "date":
        d = value if isinstance(value, date) else date.fromisoformat(str(value))
        return d.strftime("%d %b %Y")
    return str(value)


def _totals_row(table: LayoutTable) -> list[str]:
    row = []
    for i, col in enumerate(table.columns):
        if i == 0:
            row.append(f"Total ({len(table.rows)})")
        elif col.total:
            row.append(_text(sum(int(r.get(col.key) or 0) for r in table.rows), col.kind))
        elif col.kind == "percent" and table.rate_from:
            present = sum(int(r.get(table.rate_from[0]) or 0) for r in table.rows)
            working = sum(int(r.get(table.rate_from[1]) or 0) for r in table.rows)
            row.append(_text(present / working if working else None, "percent"))
        else:
            row.append("")
    return row


def _table(table: LayoutTable, width: float, font: str, bold: str):
    cols: list[Column] = table.columns
    size = 7.5 if len(cols) <= 12 else 6.8  # wide tables get a slightly smaller font
    cell = ParagraphStyle("cell", fontName=font, fontSize=size, leading=size + 1.5)
    head = ParagraphStyle("head", fontName=bold, fontSize=size, leading=size + 1.5, textColor=colors.white)
    weights = [c.width for c in cols]
    widths = [width * w / sum(weights) for w in weights]
    # Values are escaped: Paragraph understands markup, and a name containing "<" or "&"
    # must never be able to change the document.
    data = [[Paragraph(escape(c.short or c.header), head) for c in cols]]
    data += [[Paragraph(escape(_text(r.get(c.key), c.kind)), cell) for c in cols] for r in table.rows]
    if not table.rows:
        data.append([Paragraph("No data for this period.", cell)] + [""] * (len(cols) - 1))
    if table.totals and table.rows:
        data.append([Paragraph(escape(t), ParagraphStyle("tot", parent=cell, fontName=bold)) for t in _totals_row(table)])
    t = LongTable(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")]),
    ]
    if table.totals and table.rows:
        style.append(("BACKGROUND", (0, -1), (-1, -1), LIGHT))
    t.setStyle(TableStyle(style))
    return t


def build_pdf(doc: ReportDocument) -> bytes:
    font, bold = _fonts()
    out = io.BytesIO()
    page = landscape(A4)
    margin = 12 * mm
    usable = page[0] - 2 * margin

    def footer(canvas, pdf):
        canvas.saveState()
        canvas.setFont(font, 7.5)
        canvas.setFillColor(colors.grey)
        canvas.drawString(margin, 7 * mm, f"{doc.company} · {doc.title} · {doc.period}")
        canvas.drawRightString(page[0] - margin, 7 * mm, f"Page {pdf.page}")
        canvas.restoreState()

    pdf = SimpleDocTemplate(out, pagesize=page, leftMargin=margin, rightMargin=margin, topMargin=margin,
                            bottomMargin=14 * mm, title=doc.title, author=doc.company)
    h1 = ParagraphStyle("h1", fontName=bold, fontSize=16, textColor=BRAND, leading=20)
    h2 = ParagraphStyle("h2", fontName=bold, fontSize=13, leading=17)
    h3 = ParagraphStyle("h3", fontName=bold, fontSize=10.5, leading=14, spaceBefore=8, spaceAfter=4)
    meta = ParagraphStyle("meta", fontName=font, fontSize=8.5, textColor=colors.HexColor("#555555"), leading=12)

    story = [
        Paragraph(escape(doc.company), h1),
        Paragraph(escape(doc.title), h2),
        Paragraph(f"Period: {escape(doc.period)} &nbsp;·&nbsp; Generated: {escape(doc.generated_label)}"
                  f" &nbsp;·&nbsp; Covers: {escape(doc.scope)}", meta),
        Spacer(1, 6 * mm),
    ]
    # Summary as a row of boxes.
    labels = [Paragraph(escape(label), meta) for label, _, _ in doc.summary]
    values = [Paragraph(_text(v, k), ParagraphStyle("v", fontName=bold, fontSize=13, leading=16))
              for _, v, k in doc.summary]
    summary = Table([values, labels], colWidths=[usable / len(doc.summary)] * len(doc.summary))
    summary.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, GRID), ("INNERGRID", (0, 0), (-1, -1), 0.4, GRID),
                                 ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7F9FC")),
                                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story += [summary, Spacer(1, 5 * mm), Paragraph(escape(doc.main.title), h3), _table(doc.main, usable, font, bold)]
    for extra in doc.extra:
        story += [Spacer(1, 4 * mm), Paragraph(escape(extra.title), h3), _table(extra, usable * 0.6, font, bold)]

    pdf.build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()
