"""Render experiments/paper/paper.md into a clean, minimally formatted .docx.

Supported markdown subset:
  #, ##, ### headings
  plain paragraphs (with **bold** / *italic* inline spans)
  - bullet lists
  1. numbered lists
  | markdown | tables |
  ![Figure caption](relative/path.png)   -> embedded image + italic caption
  > blockquote                            -> indented italic paragraph (unused)

Run: venv39\\Scripts\\python.exe scripts/make_paper_docx.py
Output: experiments/paper/multi_field_campaign_paper.docx
"""

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PAPER_DIR = ROOT / "experiments" / "paper"
MD = PAPER_DIR / "paper.md"
OUT = PAPER_DIR / (sys.argv[1] if len(sys.argv) > 1 else "multi_field_campaign_paper.docx")

INLINE = re.compile(r"(\*\*.+?\*\*|\*[^*]+?\*|<sub>.*?</sub>|<sup>.*?</sup>)")


def add_runs(paragraph, text, base_size=None, bold=False, italic=False):
    """Add text to a paragraph, honouring **bold** / *italic* spans and
    <sub>/<sup> subscript/superscript tags (tags may nest inside spans)."""
    for tok in INLINE.split(text):
        if not tok:
            continue
        if tok.startswith("**") and tok.endswith("**") and len(tok) > 4:
            add_runs(paragraph, tok[2:-2], base_size, bold=True, italic=italic)
            continue
        if tok.startswith("*") and tok.endswith("*") and len(tok) > 2 and not tok.startswith("**"):
            add_runs(paragraph, tok[1:-1], base_size, bold=bold, italic=True)
            continue
        if tok.startswith("<sub>") and tok.endswith("</sub>"):
            run = paragraph.add_run(tok[5:-6])
            run.font.subscript = True
        elif tok.startswith("<sup>") and tok.endswith("</sup>"):
            run = paragraph.add_run(tok[5:-6])
            run.font.superscript = True
        else:
            run = paragraph.add_run(tok)
        if bold:
            run.bold = True
        if italic:
            run.italic = True
        if base_size:
            run.font.size = Pt(base_size)


def flush_table(doc, rows):
    """rows: list of lists of cell strings (header first)."""
    if not rows:
        return
    t = doc.add_table(rows=len(rows), cols=len(rows[0]))
    t.style = "Table Grid"
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            if j >= len(t.rows[i].cells):
                continue
            cell = t.rows[i].cells[j]
            cell.text = ""
            p = cell.paragraphs[0]
            add_runs(p, val, base_size=9)
            if i == 0:
                for r in p.runs:
                    r.bold = True
    doc.add_paragraph()


def main():
    if not MD.exists():
        sys.exit(f"missing {MD}")
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(6)

    lines = MD.read_text(encoding="utf-8").splitlines()
    table_buf = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        # table accumulation
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                table_buf.append(cells)
            i += 1
            continue
        if table_buf:
            flush_table(doc, table_buf)
            table_buf = []
        if not line.strip():
            i += 1
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            # Plain bold black headings (no Word heading styles -> no theme color).
            level = len(m.group(1))
            sizes = {1: 14, 2: 12, 3: 11, 4: 11}
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(10)
            add_runs(p, m.group(2))
            for r in p.runs:
                r.bold = True
                r.font.size = Pt(sizes[level])
            i += 1
            continue
        m = re.match(r"^!\[(.*)\]\((.+)\)$", line)
        if m:
            cap, rel = m.group(1), m.group(2)
            img = (PAPER_DIR / rel).resolve()
            if img.exists():
                doc.add_picture(str(img), width=Inches(6.0))
                doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            else:
                doc.add_paragraph(f"[missing figure: {rel}]")
            p = doc.add_paragraph()
            add_runs(p, cap, base_size=9)
            for r in p.runs:
                r.italic = True
            i += 1
            continue
        if line.startswith("- "):
            p = doc.add_paragraph(style="List Bullet")
            add_runs(p, line[2:])
            i += 1
            continue
        m = re.match(r"^(\d+)\.\s+(.*)$", line)
        if m:
            # Literal numbering: Word's List Number style shares one counter
            # across the document, so lists after the first start mid-sequence.
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.25)
            add_runs(p, f"{m.group(1)}. {m.group(2)}")
            i += 1
            continue
        # plain paragraph (join soft-wrapped lines)
        buf = [line]
        while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(r"^(#|\||- |\d+\. |!\[)", lines[i + 1]):
            i += 1
            buf.append(lines[i].strip())
        p = doc.add_paragraph()
        add_runs(p, " ".join(buf))
        i += 1
    if table_buf:
        flush_table(doc, table_buf)

    doc.save(OUT)
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
