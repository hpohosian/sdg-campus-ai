"""
Tables in PDFs, kept together as one piece.

Problem: PyMuPDF's plain get_text() returns a table cell by cell, one cell
per line ("1", "Solarbelt", "Kerosin", "360 t/a", ...). The chunker then
cuts such a table into ~1000-character pieces: rows lose their column
names, and a question about the WHOLE table ("which plant has the largest
capacity?") only sees part of the rows. The model answered from the first
12 of 19 rows and was wrong.

Solution: tables are found (PyMuPDF find_tables), written as a markdown
table with header row, and stored as their own chunk(s). The rest of the
page is extracted as before, without the table area, so the table text is
not in the index twice.

Only tables with drawn lines or coloured rows are detected: detection from
text alignment alone also turns normal multi-column text into "tables".
"""

import re

import fitz  # pymupdf

# A table chunk up to this size stays one chunk. Bigger tables are split by
# rows, every part with caption + header row again.
TABLE_MAX_CHARS = 4000

# MuPDF prints messages like "format error: No common ancestor in structure
# tree" for PDFs with a slightly broken accessibility structure. The text is
# read correctly anyway; real failures still raise an exception.
fitz.TOOLS.mupdf_display_errors(False)

_WS = re.compile(r"\s+")


def _cell_text(page, bbox) -> str:
    """Text of one cell. page.get_text (not the table's own extract()),
    because it keeps spaces and ligatures (fi in "Raffinerie")."""
    if not bbox:
        return ""
    text = page.get_text("text", clip=fitz.Rect(bbox))
    text = text.replace("\xad\n", "").replace("\xad", "")  # soft hyphen at line end
    text = _WS.sub(" ", text).strip()
    return text.replace("|", "/")                         # would break the markdown row


def _rows(page, table) -> list[list[str]]:
    """
    Cell texts, row by row, on a grid of our own: column borders from the
    row with the most cells, row borders from every row.

    Why not simply row.cells: tables with coloured (shaded) rows have no
    vertical lines inside those rows, so PyMuPDF returns such a row as ONE
    cell spanning the whole width. Cutting every row at the same column
    borders gives the right cells for these rows too.
    """
    rows = table.rows
    if not rows:
        return []
    best = max(rows, key=lambda r: sum(1 for c in r.cells if c))
    columns = [(c[0], c[2]) for c in best.cells if c]
    out = []
    for row in rows:
        y0, y1 = row.bbox[1], row.bbox[3]
        out.append([_cell_text(page, (x0, y0, x1, y1)) for x0, x1 in columns])
    return out


def _looks_like_table(rows: list[list[str]]) -> bool:
    """At least 2 rows x 2 columns and mostly filled cells. Rejects frames
    and layout boxes that find_tables also reports."""
    if len(rows) < 2 or max(len(r) for r in rows) < 2:
        return False
    cells = [c for r in rows for c in r]
    filled = sum(1 for c in cells if c)
    return filled >= 0.5 * len(cells)


def _caption(page, table_bbox) -> str:
    """The text block right above the table (usually its title), if close."""
    top = table_bbox[1]
    best, best_gap = "", 80.0          # at most 80 pt above the table
    for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
        gap = top - y1
        if 0 <= gap < best_gap and text.strip():
            best, best_gap = _WS.sub(" ", text).strip(), gap
    return best


def _markdown(header: list[str], rows: list[list[str]]) -> str:
    def line(cells):
        return "| " + " | ".join(cells) + " |"
    width = len(header)
    out = [line(header), line(["---"] * width)]
    out += [line((r + [""] * width)[:width]) for r in rows]
    return "\n".join(out)


_NUMBER_ONLY = re.compile(r"^[\d\s.,/%()+-]*$")


def _description(title: str, header: list[str], rows: list[list[str]]) -> str:
    """
    What the embedding model sees instead of the markdown table: title,
    column names and the name of every row (first cell that is not just a
    number). Asked "which plants have the largest capacity?", this matches
    "PtL-Produktionsanlagen ... Kapazität ..." far better than pipes and
    dashes do. Rows: 1 Solarbelt, 2 NextGate, ... -> "Solarbelt, NextGate".
    """
    columns = ", ".join(h for h in header if h)
    names = []
    for row in rows:
        name = next((c for c in row if c and not _NUMBER_ONLY.match(c)), "")
        if name and name not in names:
            names.append(name)
    text = title
    if columns:
        text += f". Spalten: {columns}"
    if names:
        text += f". Einträge: {', '.join(names)}"
    return text


def _table_chunks(caption: str, page_no: int, rows: list[list[str]]) -> list[dict]:
    """Chunk(s) of one table: {"text": markdown, "embed_text": description}.
    Very long tables are split by rows (each part with title + header)."""
    header, body = rows[0], rows[1:]
    title = f"Tabelle (Seite {page_no})" + (f": {caption}" if caption else "")

    parts, current = [], []
    for row in body:
        candidate = current + [row]
        if current and len(_markdown(header, candidate)) + len(title) > TABLE_MAX_CHARS:
            parts.append(current)
            current = [row]
        else:
            current = candidate
    if current or not parts:
        parts.append(current)

    return [
        {"text": f"{title}\n\n{_markdown(header, part)}", "embed_text": _description(title, header, part)}
        for part in parts
    ]


def extract_page(page, page_no: int) -> tuple[str, list[dict]]:
    """
    One PDF page -> (text without the tables,
                     [{"text": markdown, "embed_text": description}] per table chunk).

    Falls back to plain get_text() if table detection fails.
    """
    found = []
    # "lines_strict" (only drawn lines) first. Tables whose rows are only
    # coloured areas need "lines" (also uses the edges of filled areas);
    # which one finds such a table differs between PyMuPDF versions.
    for strategy in ("lines_strict", "lines"):
        try:
            found = page.find_tables(strategy=strategy).tables
        except Exception as e:  # table detection must never stop indexing
            print(f"[pdf_tables] page {page_no}: table detection failed: {e}")
            found = []
        if found:
            break

    tables, boxes = [], []
    for table in found:
        rows = _rows(page, table)
        if not _looks_like_table(rows):
            continue
        boxes.append(fitz.Rect(table.bbox))
        tables += _table_chunks(_caption(page, table.bbox), page_no, rows)

    if not boxes:
        return page.get_text(), []

    # Page text without the table areas (a block belongs to a table if its
    # middle lies inside the table's box).
    kept = []
    for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
        middle = fitz.Point((x0 + x1) / 2, (y0 + y1) / 2)
        if not any(middle in box for box in boxes):
            kept.append(text.strip())
    return "\n".join(t for t in kept if t), tables
