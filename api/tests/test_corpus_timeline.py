"""`corpus/TIMELINE.md` is hand-written, so it needs a check that it still describes
the corpus.

`PLAN.md` asks for a hand-verified timeline. Hand-verified means someone read it
once; it says nothing about the day a document is added and the file is not
touched. These tests are the difference between a timeline that was true and one
that is.

The gap assertion is the important one. `README.md` claimed the corpus contained
coverage gaps when it contained none, and nothing caught it because nothing was
looking — the claim described what the generator permits rather than what it
produced. If a regeneration introduces gaps, or removes the ones a future
regeneration adds, the documents that describe them must change in the same
commit. That is what this enforces.
"""

from __future__ import annotations

import collections
import csv
import datetime as dt
import itertools
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS = REPO_ROOT / "corpus"
TIMELINE = CORPUS / "TIMELINE.md"


def manifest() -> list[dict]:
    with (CORPUS / "MANIFEST.csv").open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def contracts_by_supplier() -> dict[str, list[dict]]:
    grouped = collections.defaultdict(list)
    for row in manifest():
        if row["doc_type"] == "contract":
            grouped[re.search(r"sup-(\d+)", row["doc_id"]).group(1)].append(row)
    return {k: sorted(v, key=lambda r: r["effective_from"]) for k, v in grouped.items()}


def find_gaps(grouped: dict[str, list[dict]]) -> list[tuple[str, str, str]]:
    """Periods after a supplier's first contract with nothing in force.

    Takes its input rather than reading the manifest, so it can be handed a
    corpus that *does* have gaps. Against the real corpus it has only ever
    returned an empty list, and a detector that has never once detected anything
    cannot tell "nothing to find" from "cannot find". `TestTheDetector` below is
    the known-positive.
    """
    gaps = []
    for supplier, rows in grouped.items():
        for earlier, later in itertools.pairwise(rows):
            if not earlier["effective_to"]:
                continue
            ends = dt.date.fromisoformat(earlier["effective_to"])
            starts = dt.date.fromisoformat(later["effective_from"])
            if starts > ends:
                gaps.append(
                    (supplier, earlier["effective_to"], later["effective_from"])
                )
    return gaps


def coverage_gaps() -> list[tuple[str, str, str]]:
    return find_gaps(contracts_by_supplier())


def skip_if_absent() -> bool:
    return not TIMELINE.is_file() or not (CORPUS / "MANIFEST.csv").is_file()


class TestTimelineDescribesTheCorpus:
    def test_every_document_appears(self):
        if skip_if_absent():
            return
        text = TIMELINE.read_text(encoding="utf-8")
        missing = [r["doc_id"] for r in manifest() if r["doc_id"] not in text]
        assert not missing, f"TIMELINE.md does not mention: {missing[:5]}"

    def test_it_invents_no_documents(self):
        if skip_if_absent():
            return
        known = {r["doc_id"] for r in manifest()}
        mentioned = set(
            re.findall(
                r"(?:contract|invoice|catalog|policy)-[a-z0-9-]+",
                TIMELINE.read_text(encoding="utf-8"),
            )
        )
        # Sub-strings of real ids (a prefix in prose) are not inventions.
        invented = {m for m in mentioned if not any(m in k for k in known)}
        assert not invented, (
            f"TIMELINE.md names documents not in the manifest: {invented}"
        )

    def test_contract_dates_match_the_manifest(self):
        if skip_if_absent():
            return
        text = TIMELINE.read_text(encoding="utf-8")
        for rows in contracts_by_supplier().values():
            for row in rows:
                line = next(
                    (ln for ln in text.splitlines() if row["doc_id"] in ln), None
                )
                assert line, row["doc_id"]
                assert row["effective_from"] in line, (
                    f"{row['doc_id']}: TIMELINE.md does not show "
                    f"effective_from {row['effective_from']} on its row"
                )


class TestTheDetector:
    """The known-positive. Without it, `no gaps` and `no detector` look alike."""

    @staticmethod
    def rows(*spans):
        return {
            "01": [{"effective_from": a, "effective_to": b} for a, b in spans],
        }

    def test_it_finds_a_real_gap(self):
        gaps = find_gaps(self.rows(("2024-01-01", "2025-01-01"), ("2025-03-01", None)))
        assert gaps == [("01", "2025-01-01", "2025-03-01")]

    def test_abutting_periods_are_not_a_gap(self):
        """The shape the whole corpus has: predecessor ends the day the
        successor begins, and `[from, to)` means exactly one is in force."""
        assert not find_gaps(
            self.rows(("2024-01-01", "2025-01-01"), ("2025-01-01", None))
        )

    def test_an_open_ended_predecessor_is_not_a_gap(self):
        assert not find_gaps(self.rows(("2024-01-01", None), ("2025-01-01", None)))

    def test_a_single_contract_has_no_gap_to_find(self):
        assert not find_gaps(self.rows(("2024-01-01", None)))


class TestTheGapClaim:
    def test_coverage_is_still_continuous(self):
        """If this fails, the corpus changed and three documents must change too.

        TIMELINE.md, corpus/README.md and corpus/KNOWN_ISSUES.md all state that
        coverage is continuous and that Phase 2 done-condition 4 is therefore
        unsatisfiable. Introducing a gap is the intended fix — and it makes all
        three stale in the same moment.
        """
        if skip_if_absent():
            return
        gaps = coverage_gaps()
        assert not gaps, (
            f"the corpus now has {len(gaps)} coverage gaps: {gaps[:3]}. "
            "This is the fix done-condition 4 needs — now update TIMELINE.md, "
            "corpus/README.md and corpus/KNOWN_ISSUES.md, which all say there "
            "are none."
        )

    def test_the_timeline_says_so(self):
        if skip_if_absent():
            return
        text = TIMELINE.read_text(encoding="utf-8").lower()
        assert "no coverage gaps" in text or "no gaps" in text

    def test_every_supplier_has_an_open_ended_contract(self):
        """What makes coverage continuous through AS_OF_DATE rather than merely
        gapless between documents."""
        if skip_if_absent():
            return
        for supplier, rows in contracts_by_supplier().items():
            assert not rows[-1]["effective_to"], (
                f"SUP-{supplier}'s latest contract ends "
                f"{rows[-1]['effective_to']} — there is now a period after it "
                "with nothing in force"
            )
