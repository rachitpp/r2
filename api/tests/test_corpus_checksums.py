"""`verify-corpus` must catch what it omits, not only what it lists.

The old target listed the source PDFs plus MANIFEST.csv and checked completeness
by counting PDFs, so it reported 41/41 while checking none of the 40 committed
parse artifacts. `sha256sum -c` cannot close that on its own — it verifies the
paths a file mentions and is structurally blind to the ones it does not.

So every negative case below builds a corpus, breaks it one way, and asserts the
check says which way. A checker is easier to write than to validate, and this one
is replacing a checker that was never validated.
"""

from __future__ import annotations

import corpus_checksums


def make_corpus(root):
    """The smallest thing shaped like a corpus: a manifest, a source, a parse."""
    (root / "sources" / "contracts").mkdir(parents=True)
    (root / "parsed").mkdir()
    (root / "MANIFEST.csv").write_text("doc_id\nc1\n", encoding="utf-8", newline="\n")
    (root / "sources" / "contracts" / "c1.pdf").write_bytes(b"%PDF-1.4 fake")
    (root / "parsed" / "c1.md").write_text("# C1\n", encoding="utf-8", newline="\n")
    return root


class TestArtifacts:
    def test_it_finds_every_tree_and_report(self, tmp_path):
        found = {
            p.as_posix() for p in corpus_checksums.artifacts(make_corpus(tmp_path))
        }
        assert found == {
            "MANIFEST.csv",
            "parsed/c1.md",
            "sources/contracts/c1.pdf",
        }

    def test_absent_trees_are_skipped_not_errors(self, tmp_path):
        """extracted/ and EXTRACT.csv do not exist until extraction has run."""
        corpus = make_corpus(tmp_path)
        assert not (corpus / "extracted").exists()
        assert corpus_checksums.artifacts(corpus)

    def test_extraction_output_is_picked_up_once_it_exists(self, tmp_path):
        corpus = make_corpus(tmp_path)
        (corpus / "extracted").mkdir()
        (corpus / "extracted" / "c1.json").write_text("{}", encoding="utf-8")
        (corpus / "EXTRACT.csv").write_text("doc_id\n", encoding="utf-8")
        found = {p.as_posix() for p in corpus_checksums.artifacts(corpus)}
        assert "extracted/c1.json" in found
        assert "EXTRACT.csv" in found

    def test_paths_are_posix_so_windows_and_linux_agree(self, tmp_path):
        listing = corpus_checksums.render(make_corpus(tmp_path))
        assert "\\" not in listing


class TestCheck:
    def test_a_freshly_written_corpus_passes(self, tmp_path):
        corpus = make_corpus(tmp_path)
        corpus_checksums.write_checksums(corpus)
        ok, problems = corpus_checksums.check(corpus)
        assert ok, problems

    def test_an_unlisted_artifact_fails(self, tmp_path):
        """The defect the old target had: present, committed, unchecked."""
        corpus = make_corpus(tmp_path)
        corpus_checksums.write_checksums(corpus)
        (corpus / "parsed" / "c2.md").write_text("# C2\n", encoding="utf-8")
        ok, problems = corpus_checksums.check(corpus)
        assert not ok
        assert any("unlisted" in p for p in problems)
        assert any("parsed/c2.md" in p for p in problems)

    def test_a_missing_artifact_fails(self, tmp_path):
        corpus = make_corpus(tmp_path)
        corpus_checksums.write_checksums(corpus)
        (corpus / "parsed" / "c1.md").unlink()
        ok, problems = corpus_checksums.check(corpus)
        assert not ok
        assert any("missing" in p for p in problems)

    def test_edited_content_fails(self, tmp_path):
        corpus = make_corpus(tmp_path)
        corpus_checksums.write_checksums(corpus)
        (corpus / "parsed" / "c1.md").write_text("# edited\n", encoding="utf-8")
        ok, problems = corpus_checksums.check(corpus)
        assert not ok
        assert any("do not match their checksum" in p for p in problems)

    def test_no_checksums_file_fails(self, tmp_path):
        ok, _ = corpus_checksums.check(make_corpus(tmp_path))
        assert not ok


class TestTheCommittedCorpus:
    def test_it_matches_and_lists_everything_present(self):
        corpus = corpus_checksums.CORPUS
        if not (corpus / "MANIFEST.csv").is_file():
            return  # Phase 2 has not landed here yet.
        ok, problems = corpus_checksums.check(corpus)
        assert ok, "\n".join(problems)

    def test_the_parse_output_is_actually_covered(self):
        """The specific gap, asserted by name rather than by a total.

        A count check is what let this through before — 41 listed, 41 found, and
        the 41 were the wrong files.
        """
        corpus = corpus_checksums.CORPUS
        if not (corpus / "parsed").is_dir():
            return
        listed = set(
            corpus_checksums.parse_checksums(
                (corpus / "CHECKSUMS.txt").read_text(encoding="utf-8")
            )
        )
        parsed = {f"parsed/{p.name}" for p in (corpus / "parsed").glob("*.md")}
        assert parsed and parsed <= listed, f"unlisted: {sorted(parsed - listed)[:5]}"
