#!/usr/bin/env python3
"""Render generated documents to PDF, including the deliberately hard ones.

Split from `corpus_generate.py` so that what a document *says* is decided by the
database and how it *looks* is decided here. The difficulty lives on this side:
a scan is the same content through a worse channel, and keeping that separation
means the gold set can be checked against the content layer while the pipeline is
tested against the rendered artifact.

**Byte-identity is the constraint that shapes this file.** `make ingest` run twice
must produce identical output, and a PDF writer will happily undermine that:
reportlab stamps `CreationDate` and `ModDate` with the wall clock, gives each
document a random `/ID`, and PyMuPDF does the same on save. All three are pinned
below. There is no timestamp anywhere in the output.

The scan path is: render clean → rasterise at 200dpi → rotate by a fraction of a
degree → add speckle and blur → JPEG round-trip → wrap the image back into a PDF.
That produces a document with no text layer at all, which is the point: it forces
the parse step to do OCR rather than read embedded text, and OCR is where
extraction accuracy actually gets decided.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageFilter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

#: Pinned. A wall-clock timestamp in the output would make every regeneration a
#: diff, and `make ingest` twice → byte-identical is a definition-of-done item.
PINNED_DATE = "D:20260809000000+00'00'"
SCAN_DPI = 200

MARATHI = {
    "SUPPLY AGREEMENT": "पुरवठा करार",
    "Payment terms": "देयक अटी",
    "Lead time": "पुरवठा कालावधी",
    "Returns window": "परतावा मुदत",
}


def _styles():
    sheet = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle(
            "h1",
            parent=sheet["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=15,
            spaceAfter=4 * mm,
        ),
        "meta": ParagraphStyle(
            "meta",
            parent=sheet["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=9,
            textColor=colors.HexColor("#444444"),
            spaceAfter=6 * mm,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=sheet["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            spaceBefore=3 * mm,
            spaceAfter=1 * mm,
        ),
        "body": ParagraphStyle(
            "body",
            parent=sheet["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
        ),
        "cell": ParagraphStyle(
            "cell", parent=sheet["Normal"], fontName="Helvetica", fontSize=8, leading=10
        ),
        "sig": ParagraphStyle(
            "sig",
            parent=sheet["Normal"],
            fontName="Helvetica",
            fontSize=9,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#222222"),
        ),
    }


TABLE_STYLE = TableStyle(
    [
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 8),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#333333")),
        ("LINEBELOW", (0, 1), (-1, -2), 0.2, colors.HexColor("#BBBBBB")),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
)


def _money(value) -> str:
    return f"{value:,.2f}"


def _story(doc, st) -> list:
    """Flowables for one document, from its content blocks."""
    from corpus_generate import BILINGUAL, PAGE_BREAK_TABLE, SIGNATURE, TOTALS_ABOVE

    bilingual = BILINGUAL in doc.difficulty
    story: list = []

    for kind, payload in doc.blocks:
        if kind == "heading":
            text = payload
            if bilingual and payload in MARATHI:
                text = f"{payload} / {MARATHI[payload]}"
            story.append(Paragraph(text, st["h1"]))
        elif kind == "meta":
            story.append(Paragraph(payload, st["meta"]))
        elif kind == "clauses":
            for head, body in payload:
                label = head
                if bilingual:
                    for en, mr in MARATHI.items():
                        if en.lower() in head.lower():
                            label = f"{head} / {mr}"
                story.append(Paragraph(label, st["h2"]))
                story.append(Paragraph(body, st["body"]))
        elif kind == "invoice":
            story.extend(_invoice_header(payload, st))
        elif kind == "lines":
            story.extend(
                _invoice_lines(
                    doc,
                    payload,
                    st,
                    TOTALS_ABOVE in doc.difficulty,
                    PAGE_BREAK_TABLE in doc.difficulty,
                )
            )
        elif kind == "catalog":
            story.extend(_catalog(doc, payload, st, PAGE_BREAK_TABLE in doc.difficulty))

    if SIGNATURE in doc.difficulty:
        story.append(Spacer(1, 14 * mm))
        story.append(Paragraph("_________________________", st["sig"]))
        story.append(Paragraph("Authorised signatory", st["sig"]))
    return story


def _invoice_header(row: dict, st) -> list:
    meta = [
        ["Supplier", row["supplier"], "Invoice date", f"{row['received_on']:%d %b %Y}"],
        ["Supplier code", row["code"], "Order date", f"{row['ordered_on']:%d %b %Y}"],
        [
            "Deliver to",
            f"{row['store']}, {row['city']}",
            "PO number",
            str(row["po_id"]),
        ],
    ]
    table = Table(meta, colWidths=[28 * mm, 62 * mm, 28 * mm, 42 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
                ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 8.5),
                ("FONT", (2, 0), (2, -1), "Helvetica-Bold", 8.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return [table, Spacer(1, 6 * mm)]


def _totals_block(row: dict, lines: list, st) -> Table:
    subtotal = sum(line["line_total"] for line in lines)
    table = Table(
        [["Subtotal (INR)", _money(subtotal)], ["Lines", str(len(lines))]],
        colWidths=[40 * mm, 34 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica-Bold", 9),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LINEABOVE", (0, 0), (-1, 0), 0.6, colors.HexColor("#333333")),
            ]
        )
    )
    return table


def _invoice_lines(doc, lines: list, st, totals_above: bool, span: bool) -> list:
    row = next(payload for kind, payload in doc.blocks if kind == "invoice")
    data = [["SKU", "Description", "Ordered", "Received", "Unit cost", "Line total"]]
    for line in lines:
        data.append(
            [
                line["sku"],
                Paragraph(line["product"], st["cell"]),
                str(line["quantity_ordered"]),
                str(line["quantity_received"]),
                _money(line["unit_cost"]),
                _money(line["line_total"]),
            ]
        )
    table = Table(
        data,
        colWidths=[20 * mm, 62 * mm, 17 * mm, 19 * mm, 21 * mm, 22 * mm],
        repeatRows=1,
    )
    table.setStyle(TABLE_STYLE)

    totals = _totals_block(row, lines, st)
    if totals_above:
        # The layout most likely to make an extractor bind the total to the
        # wrong thing: it appears before the rows it summarises.
        return [totals, Spacer(1, 5 * mm), table]
    out = [table, Spacer(1, 5 * mm), totals]
    if span:
        # Force the table across a page boundary rather than hoping it lands
        # there — the difficulty has to be reliable to be worth measuring.
        out = [Spacer(1, 170 * mm), table, Spacer(1, 5 * mm), totals]
    return out


def _catalog(doc, rows: list, st, span: bool) -> list:
    data = [["SKU", "Product", "Category", "Unit cost (INR)"]]
    for row in rows:
        data.append(
            [
                row["sku"],
                Paragraph(row["product"], st["cell"]),
                Paragraph(row["category"], st["cell"]),
                _money(row["unit_cost"]),
            ]
        )
    table = Table(data, colWidths=[22 * mm, 70 * mm, 44 * mm, 28 * mm], repeatRows=1)
    table.setStyle(TABLE_STYLE)
    if span:
        return [Spacer(1, 120 * mm), table]
    return [table]


def _clean_pdf(doc) -> bytes:
    buffer = io.BytesIO()
    st = _styles()
    template = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=doc.title,
        author="Kirana Retail Chain (synthetic)",
        subject=f"{doc.doc_type} — generated, not a real document",
        creator="corpus_generate.py",
        producer="corpus_generate.py",
        invariant=1,  # no random /ID, no wall-clock timestamps
    )
    template.build(_story(doc, st))
    return buffer.getvalue()


def _scan(data: bytes, doc) -> bytes:
    """Rasterise, degrade, and wrap back into a PDF with no text layer.

    Deterministic: the speckle positions come from a substream keyed on the
    document id, and the JPEG encoder is stable for identical input.
    """
    from corpus_generate import substream

    rng = substream("scan", doc.doc_id)
    source = fitz.open(stream=data, filetype="pdf")
    out = fitz.open()

    for page in source:
        pix = page.get_pixmap(dpi=SCAN_DPI, colorspace=fitz.csGRAY)
        image = Image.frombytes("L", (pix.width, pix.height), pix.samples)

        # A page fed through a sheet feeder is never quite square.
        angle = rng.uniform(-0.9, 0.9)
        image = image.rotate(angle, resample=Image.BICUBIC, fillcolor=246, expand=False)
        image = image.filter(ImageFilter.GaussianBlur(radius=0.4))

        # Speckle. Enough to matter to OCR, not enough to be unreadable.
        pixels = image.load()
        for _ in range(int(image.width * image.height * 0.0008)):
            x = rng.randrange(image.width)
            y = rng.randrange(image.height)
            pixels[x, y] = rng.choice((0, 0, 30, 60, 210))

        jpeg = io.BytesIO()
        image.save(jpeg, format="JPEG", quality=62, optimize=False)

        page_out = out.new_page(width=page.rect.width, height=page.rect.height)
        page_out.insert_image(page_out.rect, stream=jpeg.getvalue())

    # `no_new_id` here too, and it is not redundant. It PRESERVES an existing
    # /ID rather than suppressing one, so without it this intermediate save
    # stamps a random id that `_pin_metadata` then faithfully preserves — which
    # left exactly the five scanned documents varying between runs after the
    # other 35 had been fixed.
    result = out.tobytes(garbage=0, deflate=True, no_new_id=True)
    source.close()
    out.close()
    return result


def render(doc) -> bytes:
    from corpus_generate import SCANNED

    data = _clean_pdf(doc)
    if SCANNED in doc.difficulty:
        data = _scan(data, doc)
    with fitz.open(stream=data, filetype="pdf") as handle:
        doc.pages = handle.page_count
    return _pin_metadata(data)


def _pin_metadata(data: bytes) -> bytes:
    """Strip anything that varies between runs.

    PyMuPDF writes its own timestamps on save, so this runs last and pins them.
    Without it, two identical corpora differ in every file.
    """
    with fitz.open(stream=data, filetype="pdf") as handle:
        handle.set_metadata(
            {
                "producer": "corpus_generate.py",
                "creator": "corpus_generate.py",
                "creationDate": PINNED_DATE,
                "modDate": PINNED_DATE,
                "title": "",
                "author": "",
                "subject": "",
                "keywords": "",
            }
        )
        # `no_new_id` is undocumented in this version — `save.__doc__` does not
        # mention it and it is absent from the signature, which is only varargs
        # — but it is accepted and it is the difference between a reproducible
        # corpus and one that differs in every file on every run. The PDF spec
        # says the second /ID element changes whenever a file is modified, so
        # PyMuPDF regenerates it on save and that was the ONLY varying byte:
        # 31 bytes, in the trailer, in all 40 documents. Verified by
        # `make corpus-verify`, which is what keeps this honest if the flag is
        # ever dropped upstream.
        return handle.tobytes(garbage=4, deflate=True, clean=True, no_new_id=True)


MANIFEST_FIELDS = [
    "doc_id",
    "doc_type",
    "filename",
    "pages",
    "title",
    "subject",
    "effective_from",
    "effective_to",
    "source_table",
    "source_key",
    "injected_difficulty",
    "sha256",
]


def write_manifest(docs: list, out: Path) -> None:
    """One row per document, naming what it came from and what was done to it.

    `source_table` and `source_key` are the audit trail: every claim a document
    makes can be traced to the row it was generated from, which is what lets the
    gold set be checked rather than trusted.
    """
    from corpus_generate import SUBDIR

    path = out / "MANIFEST.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for doc in sorted(docs, key=lambda d: d.doc_id):
            writer.writerow(
                {
                    "doc_id": doc.doc_id,
                    "doc_type": doc.doc_type,
                    "filename": f"sources/{SUBDIR[doc.doc_type]}/{doc.filename}",
                    "pages": doc.pages,
                    "title": doc.title,
                    "subject": doc.subject,
                    "effective_from": doc.effective_from or "",
                    "effective_to": doc.effective_to or "",
                    "source_table": doc.source_table,
                    "source_key": doc.source_key,
                    "injected_difficulty": " ".join(sorted(doc.difficulty)),
                    "sha256": doc.sha256,
                }
            )
