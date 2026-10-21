"""A deliberately tiny PDF writer for layout fixtures (v4 CDR tests).

No PDF library is a dependency of this project, and committing binaries hides what a fixture contains.
This writes text at exact positions with the standard-14 fonts (Helvetica, Helvetica-Bold, Symbol),
ruled lines and URI link annotations — enough to build two-column pages, running headers and footers,
captions, equations and ruled tables whose ground truth is the code that drew them.

Coordinates are given top-left origin (like pdfplumber reports) and flipped when written.
"""
from __future__ import annotations

from dataclasses import dataclass, field

FONTS = {"F1": "Helvetica", "F2": "Helvetica-Bold", "F3": "Symbol"}


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


@dataclass
class PdfPage:
    width: float = 612
    height: float = 792
    ops: list[str] = field(default_factory=list)
    links: list[tuple[list[float], str]] = field(default_factory=list)

    def text(self, x: float, top: float, s: str, size: float = 10, font: str = "F1") -> "PdfPage":
        baseline = self.height - top - size
        self.ops.append(f"BT /{font} {size} Tf {x:.2f} {baseline:.2f} Td ({_esc(s)}) Tj ET")
        return self

    def line(self, x0: float, top0: float, x1: float, top1: float) -> "PdfPage":
        self.ops.append(f"{x0:.2f} {self.height - top0:.2f} m {x1:.2f} {self.height - top1:.2f} l S")
        return self

    def rect(self, x0: float, top: float, x1: float, bottom: float) -> "PdfPage":
        return (self.line(x0, top, x1, top).line(x1, top, x1, bottom)
                .line(x1, bottom, x0, bottom).line(x0, bottom, x0, top))

    def grid(self, x: float, top: float, col_widths: list[float], row_height: float, rows: list[list[str]],
             size: float = 9) -> "PdfPage":
        """A ruled table: every cell boxed, text inset."""
        width = sum(col_widths)
        for r in range(len(rows) + 1):
            self.line(x, top + r * row_height, x + width, top + r * row_height)
        cx = x
        for w in col_widths + [0]:
            self.line(cx, top, cx, top + len(rows) * row_height)
            cx += w
        for r, row in enumerate(rows):
            cx = x
            for c, value in enumerate(row):
                if value:
                    self.text(cx + 3, top + r * row_height + (row_height - size) / 2, value, size)
                cx += col_widths[c]
        return self

    def link(self, box: list[float], uri: str) -> "PdfPage":
        self.links.append((box, uri))
        return self


def build_pdf(pages: list[PdfPage]) -> bytes:
    objects: list[bytes] = []

    def add(body: str | bytes) -> int:
        objects.append(body.encode("latin-1") if isinstance(body, str) else body)
        return len(objects)

    catalog = add("")            # placeholders, filled once page ids are known
    pages_id = add("")
    font_ids = {k: add(f"<< /Type /Font /Subtype /Type1 /BaseFont /{v} >>") for k, v in FONTS.items()}
    fonts = " ".join(f"/{k} {i} 0 R" for k, i in font_ids.items())
    page_ids = []
    for p in pages:
        stream = "\n".join(p.ops).encode("latin-1")
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        annots = []
        for box, uri in p.links:
            x0, top, x1, bottom = box
            annots.append(add(f"<< /Type /Annot /Subtype /Link /Rect [{x0} {p.height - bottom} {x1} {p.height - top}] "
                              f"/Border [0 0 0] /A << /S /URI /URI ({_esc(uri)}) >> >>"))
        annot = f" /Annots [{' '.join(f'{a} 0 R' for a in annots)}]" if annots else ""
        page_ids.append(add(f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {p.width} {p.height}] "
                            f"/Resources << /Font << {fonts} >> >> /Contents {content} 0 R{annot} >>"))
    objects[catalog - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode()
    objects[pages_id - 1] = (f"<< /Type /Pages /Kids [{' '.join(f'{i} 0 R' for i in page_ids)}] "
                             f"/Count {len(page_ids)} >>").encode()

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


# ---------------------------------------------------------------------- the canonical layout fixture
LEFT_COL = ["Mannitol is the principal sugar", "alcohol reported in the exudate.",
            "Samples from three provinces", "were compared in this study."]
RIGHT_COL = ["Glucose and fructose were also", "detected in smaller amounts.",
             "Composition varied by region", "and by harvest season."]


def two_column_paper(pages: int = 3) -> tuple[bytes, dict]:
    """A small paper: title, running header and footer, two columns, a ruled table with caption, a display
    equation, a chemical equation, a list, a link, and a references section. Returns (bytes, ground truth)."""
    out: list[PdfPage] = []
    for n in range(1, pages + 1):
        p = PdfPage()
        p.text(72, 30, "Journal of Manna Studies - Vol 3", 8)              # running header
        p.text(300, 760, str(n), 8)                                          # page number
        if n == 1:
            p.text(150, 70, "Composition of Taranjabin Manna", 18, "F2")      # title (full width)
        y = 120
        for line in LEFT_COL:
            p.text(72, y, f"{line}", 10)
            y += 13
        y = 120
        for line in RIGHT_COL:
            p.text(330, y, f"{line}", 10)
            y += 13
        if n == 1:
            p.grid(150, 220, [120, 80, 60], 18, [["Compound", "Amount", "Unit"], ["Mannitol", "42.1", "g"],
                                                 ["Glucose", "18.7", "g"]])
            p.text(150, 280, "Table 1. Sugar content per 100 g of manna.", 9)
            p.text(200, 320, "a + b = g  (1)", 12, "F3")                     # Symbol font: a+b=g -> α+β=γ
            p.text(72, 360, "C6H12O6 + 6O2 -> 6CO2 + 6H2O", 10)
            p.text(72, 400, "- dried at room temperature", 10)
            p.text(72, 413, "- stored in sealed jars", 10)
            p.text(72, 450, "See https://example.org/manna for data.", 10)
            p.link([90, 450, 230, 461], "https://example.org/manna")
        if n == pages:
            p.text(72, 500, "References", 14, "F2")
            p.text(72, 525, "1. Smith J. Manna sugars. J Manna. 2001;3:1-9.", 9)
            p.text(72, 538, "2. Karimi A. Persian manna. Phytochem. 2010;7:22-30.", 9)
        out.append(p)
    truth = {"pages": pages, "title": "Composition of Taranjabin Manna",
             "left_first": LEFT_COL[0], "right_first": RIGHT_COL[0],
             "table_rows": [["Compound", "Amount", "Unit"], ["Mannitol", "42.1", "g"], ["Glucose", "18.7", "g"]]}
    return build_pdf(out), truth
