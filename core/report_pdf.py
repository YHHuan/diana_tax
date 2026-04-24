from __future__ import annotations

import html
import re
from io import BytesIO


class PdfExportUnavailable(RuntimeError):
    pass


def _import_reportlab():
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfbase.pdfmetrics import registerFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise PdfExportUnavailable(
            "缺少 PDF 依賴。請安裝 reportlab 後再使用 PDF 匯出。"
        ) from exc

    return {
        "colors": colors,
        "A4": A4,
        "ParagraphStyle": ParagraphStyle,
        "getSampleStyleSheet": getSampleStyleSheet,
        "mm": mm,
        "UnicodeCIDFont": UnicodeCIDFont,
        "registerFont": registerFont,
        "Paragraph": Paragraph,
        "SimpleDocTemplate": SimpleDocTemplate,
        "Spacer": Spacer,
        "Table": Table,
        "TableStyle": TableStyle,
    }


def _inline_markup(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", escaped)
    return escaped


def render_markdown_pdf(markdown_text: str, *, title: str = "Diana Tax 報稅草稿") -> bytes:
    rl = _import_reportlab()
    rl["registerFont"](rl["UnicodeCIDFont"]("STSong-Light"))

    buffer = BytesIO()
    doc = rl["SimpleDocTemplate"](
        buffer,
        pagesize=rl["A4"],
        leftMargin=16 * rl["mm"],
        rightMargin=16 * rl["mm"],
        topMargin=16 * rl["mm"],
        bottomMargin=16 * rl["mm"],
        title=title,
    )

    styles = rl["getSampleStyleSheet"]()
    body = rl["ParagraphStyle"](
        "BodyCJK",
        parent=styles["BodyText"],
        fontName="STSong-Light",
        fontSize=10.5,
        leading=15,
        spaceAfter=6,
    )
    h1 = rl["ParagraphStyle"](
        "Heading1CJK",
        parent=styles["Heading1"],
        fontName="STSong-Light",
        fontSize=18,
        leading=24,
        spaceAfter=10,
    )
    h2 = rl["ParagraphStyle"](
        "Heading2CJK",
        parent=styles["Heading2"],
        fontName="STSong-Light",
        fontSize=14,
        leading=18,
        spaceAfter=8,
    )
    h3 = rl["ParagraphStyle"](
        "Heading3CJK",
        parent=styles["Heading3"],
        fontName="STSong-Light",
        fontSize=12,
        leading=16,
        spaceAfter=6,
    )
    quote = rl["ParagraphStyle"](
        "QuoteCJK",
        parent=body,
        leftIndent=14,
        textColor=rl["colors"].grey,
    )

    story = []
    lines = markdown_text.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()

        if not stripped:
            story.append(rl["Spacer"](1, 4))
            i += 1
            continue

        if stripped.startswith("|") and i + 1 < len(lines) and lines[i + 1].strip().startswith("|---"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                raw_cells = [cell.strip() for cell in lines[i].strip().strip("|").split("|")]
                if not all(set(cell) <= {"-"} for cell in raw_cells):
                    rows.append(raw_cells)
                i += 1
            table = rl["Table"](rows, repeatRows=1)
            table.setStyle(
                rl["TableStyle"](
                    [
                        ("FONTNAME", (0, 0), (-1, -1), "STSong-Light"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("LEADING", (0, 0), (-1, -1), 12),
                        ("BACKGROUND", (0, 0), (-1, 0), rl["colors"].lightgrey),
                        ("GRID", (0, 0), (-1, -1), 0.4, rl["colors"].grey),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            story.append(table)
            story.append(rl["Spacer"](1, 8))
            continue

        if stripped.startswith("# "):
            story.append(rl["Paragraph"](_inline_markup(stripped[2:].strip()), h1))
        elif stripped.startswith("## "):
            story.append(rl["Paragraph"](_inline_markup(stripped[3:].strip()), h2))
        elif stripped.startswith("### "):
            story.append(rl["Paragraph"](_inline_markup(stripped[4:].strip()), h3))
        elif stripped.startswith(">"):
            story.append(rl["Paragraph"](_inline_markup(stripped[1:].strip()), quote))
        else:
            story.append(rl["Paragraph"](_inline_markup(stripped), body))
        i += 1

    doc.build(story)
    return buffer.getvalue()
