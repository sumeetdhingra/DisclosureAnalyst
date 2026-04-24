"""Render the markdown analysis report into a styled PDF.

Produces a layout that matches the reference "Disclosure Package Summary"
sample: blue numbered section headings, blue sub-headings, bordered key/value
and multi-column tables, true round bullets with hanging indent, and italic
small notes.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


BLUE = colors.HexColor("#1a365d")
SUBTLE = colors.HexColor("#666666")
TABLE_HEAD_BG = colors.HexColor("#f1f5f9")
TABLE_GRID = colors.HexColor("#cbd5e1")


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=26, leading=30, spaceAfter=4, textColor=BLUE,
            alignment=TA_LEFT,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle", parent=base["Normal"], fontName="Helvetica",
            fontSize=10.5, leading=13, textColor=SUBTLE, spaceAfter=14,
        ),
        "scope": ParagraphStyle(
            "Scope", parent=base["Normal"], fontName="Helvetica",
            fontSize=8.5, leading=11, textColor=SUBTLE,
            spaceBefore=6, spaceAfter=10,
        ),
        "h1": ParagraphStyle(  # numbered section, e.g. "1. Key Inspection Findings"
            "H1", parent=base["Heading1"], fontName="Helvetica-Bold",
            fontSize=18, leading=22, spaceBefore=18, spaceAfter=8,
            textColor=BLUE,
        ),
        "h2": ParagraphStyle(  # blue sub-heading
            "H2", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=12, leading=16, spaceBefore=10, spaceAfter=4,
            textColor=BLUE,
        ),
        "h3": ParagraphStyle(
            "H3", parent=base["Heading3"], fontName="Helvetica-Bold",
            fontSize=10.5, leading=14, spaceBefore=6, spaceAfter=3,
            textColor=colors.HexColor("#2d3748"),
        ),
        "body": ParagraphStyle(
            "Body", parent=base["BodyText"], fontName="Helvetica",
            fontSize=10, leading=13.5, spaceAfter=6, alignment=TA_LEFT,
            textColor=colors.black,
        ),
        "bullet": ParagraphStyle(
            "Bullet", parent=base["BodyText"], fontName="Helvetica",
            fontSize=10, leading=13.5, spaceAfter=3,
            leftIndent=18, bulletIndent=6,
            textColor=colors.black,
        ),
        "tbl_head": ParagraphStyle(
            "TblHead", parent=base["BodyText"], fontName="Helvetica-Bold",
            fontSize=10, leading=12, textColor=colors.black,
        ),
        "tbl_cell": ParagraphStyle(
            "TblCell", parent=base["BodyText"], fontName="Helvetica",
            fontSize=9.5, leading=12, textColor=colors.black,
        ),
        "tbl_label": ParagraphStyle(
            "TblLabel", parent=base["BodyText"], fontName="Helvetica-Bold",
            fontSize=9.5, leading=12, textColor=colors.black,
        ),
        "note": ParagraphStyle(
            "Note", parent=base["BodyText"], fontName="Helvetica",
            fontSize=8.5, leading=11, textColor=SUBTLE,
            spaceBefore=4, spaceAfter=8,
        ),
    }


_INLINE_BOLD = re.compile(r"\*\*(.+?)\*\*")
_INLINE_ITAL = re.compile(r"(?<!\*)\*(?!\*)([^*\n]+?)\*(?!\*)")
_INLINE_CODE = re.compile(r"`([^`]+)`")
_NUM_HEAD = re.compile(r"^(\d+)\.\s+(.+)$")


def _inline(md: str) -> str:
    s = (md.replace("&", "&amp;")
           .replace("<", "&lt;")
           .replace(">", "&gt;"))
    s = _INLINE_BOLD.sub(r"<b>\1</b>", s)
    s = _INLINE_ITAL.sub(r"<i>\1</i>", s)
    s = _INLINE_CODE.sub(r"<font face='Courier'>\1</font>", s)
    return s


def _is_table_row(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.endswith("|") and s.count("|") >= 2


def _is_table_separator(line: str) -> bool:
    s = line.strip()
    if not _is_table_row(s):
        return False
    cells = [c.strip() for c in s.strip("|").split("|")]
    return all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c)


def _parse_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _build_table(rows: list[list[str]], styles, available_width: float):
    if not rows:
        return None
    n_cols = max(len(r) for r in rows)
    rows = [r + [""] * (n_cols - len(r)) for r in rows]

    # First row treated as header
    head = [Paragraph(_inline(c), styles["tbl_head"]) for c in rows[0]]
    body = []
    for r in rows[1:]:
        body.append([Paragraph(_inline(c), styles["tbl_cell"]) for c in r])

    # Column widths: first column narrower for 2-col key/value, otherwise share
    if n_cols == 2:
        col_widths = [available_width * 0.32, available_width * 0.68]
    elif n_cols == 3:
        col_widths = [available_width * 0.5, available_width * 0.2,
                      available_width * 0.3]
    else:
        col_widths = [available_width / n_cols] * n_cols

    data = [head] + body
    tbl = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TABLE_HEAD_BG),
        ("GRID", (0, 0), (-1, -1), 0.5, TABLE_GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return tbl


def _markdown_to_flowables(md: str, styles, available_width: float):
    story: list = []
    para_buf: list[str] = []
    table_buf: list[str] = []

    def flush_para():
        if para_buf:
            text = " ".join(para_buf).strip()
            # "Scope note." / "Flags." / "Caveats." style — render small grey
            if re.match(r"^(Scope note|Flags?|Caveats?|Warranty limitations|"
                        r"Ambiguity flagged|Clearance ambiguity flagged|"
                        r"Document-availability flags|Note)\b", text):
                story.append(Paragraph(_inline(text), styles["note"]))
            else:
                story.append(Paragraph(_inline(text), styles["body"]))
            para_buf.clear()

    def flush_table():
        if not table_buf:
            return
        rows = []
        for line in table_buf:
            if _is_table_separator(line):
                continue
            rows.append(_parse_row(line))
        tbl = _build_table(rows, styles, available_width)
        if tbl is not None:
            story.append(Spacer(1, 4))
            story.append(tbl)
            story.append(Spacer(1, 6))
        table_buf.clear()

    lines = md.splitlines()
    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        # Table accumulation
        if _is_table_row(stripped):
            flush_para()
            table_buf.append(stripped)
            continue
        else:
            flush_table()

        if not stripped:
            flush_para()
            continue

        # Headings
        if stripped.startswith("## "):
            flush_para()
            head_text = stripped[3:].strip()
            m = _NUM_HEAD.match(head_text)
            if m:
                story.append(Paragraph(
                    f"{m.group(1)}. {_inline(m.group(2))}", styles["h1"]))
            else:
                story.append(Paragraph(_inline(head_text), styles["h1"]))
            continue
        if stripped.startswith("### "):
            flush_para()
            story.append(Paragraph(_inline(stripped[4:].strip()), styles["h2"]))
            continue
        if stripped.startswith("#### "):
            flush_para()
            story.append(Paragraph(_inline(stripped[5:].strip()), styles["h3"]))
            continue
        if stripped.startswith("# "):
            flush_para()
            story.append(Paragraph(_inline(stripped[2:].strip()), styles["h1"]))
            continue

        # Bullets
        if stripped.startswith(("- ", "* ", "+ ")):
            flush_para()
            text = stripped[2:].strip()
            story.append(Paragraph(
                _inline(text), styles["bullet"], bulletText="\u2022"))
            continue

        # Numbered list (only if not a heading) — render with the number
        m = re.match(r"^(\d+)\.\s+(.*)", stripped)
        if m and not stripped.startswith("## "):
            flush_para()
            story.append(Paragraph(
                f"{m.group(1)}. {_inline(m.group(2))}", styles["body"]))
            continue

        # Horizontal rule
        if re.fullmatch(r"-{3,}|\*{3,}|_{3,}", stripped):
            flush_para()
            story.append(Spacer(1, 6))
            continue

        para_buf.append(stripped)

    flush_para()
    flush_table()
    return story


def render_pdf(markdown_text: str, out_path: Path,
               source_zip_name: str | None = None) -> Path:
    out_path = Path(out_path)
    left = right = 0.75 * inch
    top = bottom = 0.75 * inch
    doc = SimpleDocTemplate(
        str(out_path), pagesize=LETTER,
        leftMargin=left, rightMargin=right,
        topMargin=top, bottomMargin=bottom,
        title="Disclosure Analysis Report",
        author="Disclosure Analyst",
    )
    available_width = LETTER[0] - left - right
    styles = _styles()

    story = [
        Paragraph("Disclosure Analysis Report", styles["title"]),
        Paragraph(
            f"Generated {datetime.now().strftime('%B %d, %Y at %I:%M %p')}"
            + (f"  &middot;  Source: {source_zip_name}" if source_zip_name else ""),
            styles["subtitle"],
        ),
    ]
    story.extend(_markdown_to_flowables(markdown_text, styles, available_width))
    doc.build(story)
    return out_path
