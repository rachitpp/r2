#!/usr/bin/env python3
"""Write and check `corpus/CHECKSUMS.txt`.

`CONVENTIONS.md` and ADR-0006 both say `verify-corpus` SHA-256s every file in
`parsed/` and `extracted/`. **It never did.** It listed the 40 source PDFs plus
`MANIFEST.csv`, and its completeness check counted PDFs — so it passed 41/41
while checking none of the parse output, which was committed and unverified for
the whole of Phase 2. A check that is not running wearing the label of one that
is, in the target whose entire job is being that check.

Two things are needed to close it and only one is obvious:

1. Hash the parse and extraction artifacts too. Obvious.
2. **Assert that the set of listed files equals the set of files present.**
   Without this, an artifact added and not listed is silently unchecked — which
   is exactly how the gap survived. `sha256sum -c` alone cannot catch it: it
   verifies what the file mentions and is blind to what it omits.

The output format is unchanged — `<sha256>  <path>`, relative to `corpus/` — so
`cd corpus && sha256sum -c CHECKSUMS.txt` still works by hand.

**Ownership.** The last pipeline stage to touch artifacts refreshes this file:
`corpus_ingest.py` calls `write_checksums` on a canonical run. `make corpus`
alone leaves it stale, which is correct and harmless because regenerating the
documents always requires re-parsing them anyway — and `--check` says so rather
than just failing.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS = REPO_ROOT / "corpus"

#: Directories of committed artifacts, and the glob that matches them. Adding a
#: pipeline stage means adding a line here — and if you forget, --check fails
#: with the unlisted files named, rather than passing quietly.
ARTIFACT_TREES = (
    ("sources", "**/*.pdf"),
    ("parsed", "*.md"),
    ("extracted", "*.json"),
)

#: Reports that describe the corpus. Absent ones are skipped, not an error:
#: EXTRACT.csv does not exist until extraction has run.
ARTIFACT_FILES = ("MANIFEST.csv", "PARSE.csv", "EXTRACT.csv")


def artifacts(corpus: Path) -> list[Path]:
    """Every committed artifact present, as paths relative to `corpus`."""
    found: list[Path] = []
    for directory, pattern in ARTIFACT_TREES:
        root = corpus / directory
        if root.is_dir():
            found += [p.relative_to(corpus) for p in root.glob(pattern) if p.is_file()]
    found += [Path(name) for name in ARTIFACT_FILES if (corpus / name).is_file()]
    # as_posix so a Windows run and a Linux run produce the same file.
    return sorted(found, key=lambda p: p.as_posix())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(corpus: Path) -> str:
    return (
        "\n".join(
            f"{digest(corpus / rel)}  {rel.as_posix()}" for rel in artifacts(corpus)
        )
        + "\n"
    )


def write_checksums(corpus: Path = CORPUS) -> int:
    """Regenerate CHECKSUMS.txt from what is on disk. Returns the file count."""
    body = render(corpus)
    # newline="\n" for the reason in corpus_ingest: this file is itself hashed
    # by nothing, but it is compared byte-for-byte across platforms and a CRLF
    # copy would make every Windows regeneration look like a change.
    (corpus / "CHECKSUMS.txt").write_text(body, encoding="utf-8", newline="\n")
    return len(body.strip().splitlines())


def parse_checksums(text: str) -> dict[str, str]:
    entries = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        sha, _, path = line.partition("  ")
        entries[path.strip()] = sha.strip()
    return entries


def check(corpus: Path = CORPUS) -> tuple[bool, list[str]]:
    """Verify hashes AND completeness. Returns (ok, messages)."""
    listing = corpus / "CHECKSUMS.txt"
    if not listing.is_file():
        return False, [f"{listing} does not exist"]

    listed = parse_checksums(listing.read_text(encoding="utf-8"))
    present = {p.as_posix() for p in artifacts(corpus)}
    problems: list[str] = []

    unlisted = sorted(present - set(listed))
    if unlisted:
        problems.append(
            f"{len(unlisted)} artifacts are present but unlisted — an unlisted "
            f"file is one the pipeline reads and nothing checks:"
        )
        problems += [f"    {name}" for name in unlisted[:10]]
        problems.append("  Run `make corpus-checksums` if this is intended.")

    missing = sorted(set(listed) - present)
    if missing:
        problems.append(f"{len(missing)} listed artifacts are missing from disk:")
        problems += [f"    {name}" for name in missing[:10]]

    changed = [
        name
        for name in sorted(present & set(listed))
        if digest(corpus / name) != listed[name]
    ]
    if changed:
        problems.append(f"{len(changed)} artifacts do not match their checksum:")
        problems += [f"    {name}" for name in changed[:10]]

    return not problems, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=str(CORPUS))
    parser.add_argument(
        "--check", action="store_true", help="verify instead of regenerating"
    )
    args = parser.parse_args(argv)
    corpus = Path(args.corpus)

    if not (corpus / "MANIFEST.csv").is_file():
        print("skip: no corpus yet (Phase 2)")
        return 0

    if args.check:
        ok, problems = check(corpus)
        for line in problems:
            print(line)
        if ok:
            total = len(artifacts(corpus))
            print(f"corpus matches CHECKSUMS.txt — {total} artifacts, none unlisted")
        return 0 if ok else 1

    total = write_checksums(corpus)
    print(f"wrote corpus/CHECKSUMS.txt — {total} artifacts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
