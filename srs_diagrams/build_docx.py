import re, os
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

SRS_PATH = r"f:\spl3\SRS.md"
DIAG_DIR = r"f:\spl3\srs_diagrams"
OUT_PATH = r"f:\spl3\SRS.docx"

with open(SRS_PATH, encoding="utf-8") as f:
    text = f.read()

doc = Document()

# Base style
style = doc.styles['Normal']
style.font.name = 'Calibri'
style.font.size = Pt(10.5)

def add_heading(text_, level):
    h = doc.add_heading(text_, level=level)
    return h

def set_cell_shading(cell, color_hex):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), color_hex)
    tcPr.append(shd)

def add_table(rows):
    if not rows:
        return
    table = doc.add_table(rows=1, cols=len(rows[0]))
    table.style = 'Light Grid Accent 1'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr_cells = table.rows[0].cells
    for i, cell_text in enumerate(rows[0]):
        hdr_cells[i].text = cell_text
        for p in hdr_cells[i].paragraphs:
            for r in p.runs:
                r.bold = True
        set_cell_shading(hdr_cells[i], "2F5496")
        for p in hdr_cells[i].paragraphs:
            for r in p.runs:
                r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    for row in rows[1:]:
        cells = table.add_row().cells
        for i, cell_text in enumerate(row):
            cells[i].text = cell_text
    doc.add_paragraph()

def add_inline_markdown(paragraph, segment):
    # handle **bold** and `code` inline within a run of text
    tokens = re.split(r'(\*\*.*?\*\*|`.*?`)', segment)
    for tok in tokens:
        if not tok:
            continue
        if tok.startswith('**') and tok.endswith('**'):
            run = paragraph.add_run(tok[2:-2])
            run.bold = True
        elif tok.startswith('`') and tok.endswith('`'):
            run = paragraph.add_run(tok[1:-1])
            run.font.name = 'Consolas'
            run.font.size = Pt(9.5)
        else:
            paragraph.add_run(tok)

def parse_table_block(lines):
    rows = []
    for line in lines:
        line = line.strip()
        if not line.startswith('|'):
            continue
        if re.match(r'^\|[\s:\-|]+\|$', line):
            continue
        cells = [c.strip() for c in line.strip('|').split('|')]
        rows.append(cells)
    return rows

diagram_counter = 0
lines = text.split('\n')
i = 0
in_mermaid = False
mermaid_lines = []
table_buffer = []
toc_skip = False

while i < len(lines):
    line = lines[i]

    # Skip the manual TOC block (we rely on headings/Word TOC instead)
    if line.strip() == '## Table of Contents':
        toc_skip = True
        i += 1
        continue
    if toc_skip:
        if line.startswith('## ') and line.strip() != '## Table of Contents':
            toc_skip = False
        else:
            i += 1
            continue

    # Mermaid code block -> replace with rendered image
    if line.strip() == '```mermaid':
        in_mermaid = True
        mermaid_lines = []
        i += 1
        continue
    if in_mermaid:
        if line.strip() == '```':
            in_mermaid = False
            img_path = os.path.join(DIAG_DIR, f"diagram_{diagram_counter:02d}.png")
            if os.path.exists(img_path):
                doc.add_picture(img_path, width=Inches(6.3))
                last_p = doc.paragraphs[-1]
                last_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            else:
                p = doc.add_paragraph(f"[Diagram {diagram_counter} image not found: {img_path}]")
                p.italic = True
            diagram_counter += 1
            i += 1
            continue
        else:
            mermaid_lines.append(line)
            i += 1
            continue

    # Generic fenced code block (non-mermaid)
    if line.strip().startswith('```') and not in_mermaid:
        i += 1
        code_lines = []
        while i < len(lines) and not lines[i].strip().startswith('```'):
            code_lines.append(lines[i])
            i += 1
        i += 1  # skip closing ```
        for cl in code_lines:
            p = doc.add_paragraph(cl)
            for r in p.runs:
                r.font.name = 'Consolas'
                r.font.size = Pt(9)
            p.paragraph_format.space_after = Pt(0)
        doc.add_paragraph()
        continue

    # Table block
    if line.strip().startswith('|'):
        table_lines = []
        while i < len(lines) and lines[i].strip().startswith('|'):
            table_lines.append(lines[i])
            i += 1
        rows = parse_table_block(table_lines)
        add_table(rows)
        continue

    # Headings
    m = re.match(r'^(#{1,4})\s+(.*)$', line)
    if m:
        level = len(m.group(1))
        heading_text = m.group(2).strip()
        # docx supports heading levels 1-9, but title page level should map level-1 -> level
        add_heading(heading_text, min(level, 4))
        i += 1
        continue

    # Horizontal rule
    if line.strip() == '---':
        i += 1
        continue

    # Blockquote
    if line.strip().startswith('>'):
        p = doc.add_paragraph(line.strip().lstrip('>').strip())
        p.italic = True
        for r in p.runs:
            r.italic = True
            r.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
        i += 1
        continue

    # Bullet list
    if re.match(r'^\s*-\s+', line):
        content_ = re.sub(r'^\s*-\s+', '', line)
        p = doc.add_paragraph(style='List Bullet')
        add_inline_markdown(p, content_)
        i += 1
        continue

    # Numbered list
    if re.match(r'^\s*\d+\.\s+', line):
        content_ = re.sub(r'^\s*\d+\.\s+', '', line)
        p = doc.add_paragraph(style='List Number')
        add_inline_markdown(p, content_)
        i += 1
        continue

    # Blank line
    if line.strip() == '':
        i += 1
        continue

    # Bold standalone line e.g. *End of ...*
    if line.strip().startswith('*') and line.strip().endswith('*') and not line.strip().startswith('**'):
        p = doc.add_paragraph()
        run = p.add_run(line.strip().strip('*'))
        run.italic = True
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        i += 1
        continue

    # Normal paragraph
    p = doc.add_paragraph()
    add_inline_markdown(p, line.strip())
    i += 1

doc.save(OUT_PATH)
print(f"Saved {OUT_PATH}, embedded {diagram_counter} diagrams")
