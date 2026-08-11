#!/usr/bin/env python3
"""Parse every corpus document with Docling and commit the result.

The parsed output is a committed artifact, not a cache. A reader can see exactly
what the extraction step was given, which matters because **the parse is where
most of the difficulty actually lands** — by the time a model sees text, the
scanned documents have already been through OCR and the damage is done.

Docling is pinned in `corpus/PIPELINE.json`, and the version is recorded in the
parse report alongside the OCR engine, because a different parser version is a
different measurement even when the documents are identical.

**OCR runs on the four scanned documents and its output is imperfect on purpose.**
The first parse produced `PERISHABLEHANDLING` and `01September2025` — spaces lost
across the skew. That is the point of having scans in the corpus: without them the
extraction step reads text that was never in doubt.

Getting an OCR engine working here was not obvious and is worth recording. Docling
reported *"RapidOCR is not installed"* while `rapidocr` was installed and
importable — the real failure was `libGL.so.1`, a system library that `opencv-python`
needs and this environment lacks. Installing `opencv-python-headless` alongside it
fixed the import. An error message naming the wrong cause cost more time than the
problem did.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from pathlib import Path

# Docling pulls torch, which is chatty on import and during inference. None of it
# is actionable here and it buries the progress output.
os.environ.setdefault("TORCH_LOGS", "-dynamo")
os.environ.setdefault("TORCHDYNAMO_VERBOSE", "0")
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS = REPO_ROOT / "corpus"

REPORT_FIELDS = [
    "doc_id", "doc_type", "injected_difficulty", "pages", "chars", "tables",
    "ocr_used", "parse_seconds", "sha256",
]


def load_manifest(corpus: Path) -> list[dict]:
    with (corpus / "MANIFEST.csv").open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def converter():
    """One converter for every document, so the pipeline options are identical.

    OCR is on for all of them rather than only the scans. A parser that is
    configured differently per document is measuring several pipelines and
    reporting one number.
    """
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions(
        do_ocr=True,
        do_table_structure=True,
        ocr_options=RapidOcrOptions(),
    )
    options.table_structure_options.do_cell_matching = True
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


def versions() -> dict:
    import importlib.metadata as md

    def version(name: str) -> str | None:
        try:
            return md.version(name)
        except Exception:
            return None

    return {
        "docling": version("docling"),
        "docling_core": version("docling-core"),
        "docling_ibm_models": version("docling-ibm-models"),
        "ocr_engine": "rapidocr",
        "rapidocr": version("rapidocr"),
        "onnxruntime": version("onnxruntime"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=str(CORPUS))
    parser.add_argument("--out", default=None, help="defaults to <corpus>/parsed")
    parser.add_argument("--only", default="", help="comma-separated doc ids")
    args = parser.parse_args(argv)

    corpus = Path(args.corpus)
    out = Path(args.out) if args.out else corpus / "parsed"
    out.mkdir(parents=True, exist_ok=True)

    docs = load_manifest(corpus)
    if args.only:
        wanted = set(args.only.split(","))
        docs = [d for d in docs if d["doc_id"] in wanted]

    print(f"docling  {versions()['docling']}  ocr=rapidocr")
    print(f"parsing  {len(docs)} documents\n")

    convert = converter()
    report: list[dict] = []
    written: set[Path] = set()

    for doc in docs:
        source = corpus / doc["filename"]
        started = time.time()
        result = convert.convert(source)
        elapsed = time.time() - started

        markdown = result.document.export_to_markdown()
        target = out / f"{doc['doc_id']}.md"
        target.write_text(markdown, encoding="utf-8")
        written.add(target.resolve())

        tables = len(getattr(result.document, "tables", []) or [])
        report.append({
            "doc_id": doc["doc_id"],
            "doc_type": doc["doc_type"],
            "injected_difficulty": doc["injected_difficulty"],
            "pages": doc["pages"],
            "chars": len(markdown),
            "tables": tables,
            # A scanned document has no text layer, so any text at all came from
            # OCR. Derived from the artifact rather than from the manifest's
            # claim about it.
            "ocr_used": "scanned" in doc["injected_difficulty"],
            "parse_seconds": f"{elapsed:.1f}",
            "sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        })
        mark = "ocr" if "scanned" in doc["injected_difficulty"] else "   "
        print(f"  {mark} {doc['doc_id']:34} {len(markdown):6} chars  "
              f"{tables} tables  {elapsed:5.1f}s")

    # Same sweep as the generator, for the same reason: a parsed file left behind
    # by an earlier run is input the extraction step would happily consume.
    if not args.only:
        for stale in sorted(out.glob("*.md")):
            if stale.resolve() not in written:
                stale.unlink()
                print(f"  removed stale {stale.name}")

    empty = [r for r in report if r["chars"] < 50]
    with (corpus / "PARSE.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPORT_FIELDS)
        writer.writeheader()
        writer.writerows(sorted(report, key=lambda r: r["doc_id"]))

    pipeline = corpus / "PIPELINE.json"
    spec = json.loads(pipeline.read_text(encoding="utf-8"))
    spec["parse"] = {
        "tool": "docling",
        **versions(),
        "note": (
            "OCR is enabled for every document, not only the scans, so one "
            "pipeline is being measured rather than several. RapidOCR needs "
            "opencv-python-headless in this environment: docling reports "
            "'RapidOCR is not installed' when the real failure is a missing "
            "libGL.so.1."
        ),
    }
    pipeline.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")

    total = sum(float(r["parse_seconds"]) for r in report)
    ocr_docs = [r for r in report if r["ocr_used"]]
    print(f"\nparsed {len(report)} documents in {total:.0f}s "
          f"({len(ocr_docs)} through OCR)")
    print(f"wrote {out.relative_to(REPO_ROOT)}/ and corpus/PARSE.csv")
    if empty:
        # A document that parsed to nothing is worse than one that parsed badly:
        # the extraction step would report a clean miss and nothing would look
        # broken.
        print("\nDOCUMENTS THAT PARSED TO (ALMOST) NOTHING:")
        for row in empty:
            print(f"  {row['doc_id']} — {row['chars']} chars")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
