"""Guards for three defects in the parse step, all found on 2026-08-11.

None of them was caught by anything: the parse produced output, the run looked
successful, and two of the three corrupted a committed artifact while doing it.
That is the project's recurring class — a check that is not running wearing the
label of one that is — so each fix gets an assertion rather than a note.

Importing the module is cheap: docling is imported inside `converter()`, not at
module scope, so these tests need neither the corpus nor the model weights.
"""

from __future__ import annotations

from pathlib import Path

import corpus_ingest


class TestDisplay:
    """`--out` outside the repo crashed the run in its final print statement."""

    def test_repo_relative_when_inside(self):
        inside = corpus_ingest.REPO_ROOT / "corpus" / "parsed"
        assert corpus_ingest.display(inside) == str(Path("corpus/parsed"))

    def test_falls_back_instead_of_raising(self, tmp_path):
        """The exact case `make ingest-verify` passes: mktemp -d.

        `Path.relative_to` raises rather than falling back, and the crash landed
        *after* every file had been written — so the Makefile's `&&` meant the
        byte-comparison the target exists for never ran at all.
        """
        assert corpus_ingest.display(tmp_path) == str(tmp_path)


class TestIsCanonical:
    """Only a whole-corpus run into the canonical location writes the report."""

    def test_full_run_into_the_corpus_is_canonical(self, tmp_path):
        assert corpus_ingest.is_canonical(
            only="", out=tmp_path / "parsed", corpus=tmp_path
        )

    def test_only_is_not_canonical(self, tmp_path):
        """A partial run truncated PARSE.csv from 40 rows to 1."""
        assert not corpus_ingest.is_canonical(
            only="contract-sup-01-20241130", out=tmp_path / "parsed", corpus=tmp_path
        )

    def test_out_elsewhere_is_not_canonical(self, tmp_path):
        """What ingest-verify does — the verification must not mutate the corpus."""
        assert not corpus_ingest.is_canonical(
            only="", out=tmp_path / "somewhere-else", corpus=tmp_path
        )


class TestParsedOutputIsLineEndingStable:
    """PARSE.csv hashes the in-memory string; the file on disk must match it.

    Without `newline="\\n"` Python translates every newline on Windows, so the
    recorded sha256 described a file that did not exist. `verify-corpus` cannot
    catch it either, because `parsed/` is not in CHECKSUMS.txt.
    """

    def test_committed_parse_has_no_crlf(self):
        parsed = corpus_ingest.REPO_ROOT / "corpus" / "parsed"
        if not parsed.is_dir():
            return  # Phase 2 has not landed here yet.
        offenders = [
            p.name for p in sorted(parsed.glob("*.md")) if b"\r\n" in p.read_bytes()
        ]
        assert not offenders, f"CRLF in committed parse output: {offenders}"

    def test_recorded_hashes_describe_the_files_on_disk(self):
        """The known-positive this probe would otherwise lack.

        A hash column that is never compared against its artifact cannot tell
        "nothing drifted" from "nothing was checked".
        """
        import csv
        import hashlib

        corpus = corpus_ingest.REPO_ROOT / "corpus"
        report = corpus / "PARSE.csv"
        if not report.is_file():
            return  # Phase 2 has not landed here yet.

        rows = list(csv.DictReader(report.open(encoding="utf-8")))
        assert rows, "PARSE.csv is empty — a partial run may have truncated it"

        mismatched = []
        for row in rows:
            artifact = corpus / "parsed" / f"{row['doc_id']}.md"
            actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
            if actual != row["sha256"]:
                mismatched.append(row["doc_id"])
        assert not mismatched, f"PARSE.csv hash does not match the file: {mismatched}"

    def test_the_report_covers_every_document_in_the_manifest(self):
        """`--only` used to overwrite PARSE.csv with just the documents it ran."""
        import csv

        corpus = corpus_ingest.REPO_ROOT / "corpus"
        if not (corpus / "PARSE.csv").is_file():
            return  # Phase 2 has not landed here yet.

        parsed = {
            r["doc_id"]
            for r in csv.DictReader((corpus / "PARSE.csv").open(encoding="utf-8"))
        }
        manifest = {
            r["doc_id"]
            for r in csv.DictReader((corpus / "MANIFEST.csv").open(encoding="utf-8"))
        }
        assert parsed == manifest, (
            f"PARSE.csv covers {len(parsed)} of the manifest's {len(manifest)} "
            f"documents; missing {sorted(manifest - parsed)[:5]}"
        )
