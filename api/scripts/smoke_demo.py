"""Drive both demo beats through the web app's own request path. No model calls.

**Why this exists.** Everything else in this repo tests one side of the boundary:
`pytest` exercises FastAPI through `TestClient`, `tsc` and `next build` check the
web app compiles. Neither touches the thing between them — the Next rewrite in
`next.config.ts` that turns `/api/ask` into `http://127.0.0.1:8000/ask`. A typo
there breaks every request in the browser while both test suites stay green.

So this hits **port 3000, not 8000**, deliberately. It is the only check in the
project that would notice the proxy being wrong.

**What it does NOT cover, and the gap is real:** React event wiring. A button
whose `onClick` was never attached, or a `useState` that never re-renders, passes
everything here and everything in CI. Verifying that needs a browser driving the
page, and the honest state of this project is that nobody has done it — say so
rather than letting a green smoke run imply otherwise.

Run `make serve` and `make web` first, then `make smoke`. DEMO_MODE=true, so no
key and no quota: retrieval runs for real because embeddings are local, and the
answer text is replayed.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

WEB = "http://127.0.0.1:3000"

# The three cases demo beat 2 exists to show, plus the two refusals. Each names
# what it proves, because a smoke test that only reports pass/fail teaches
# nothing when it fails.
CASES = [
    {
        "name": "before the renegotiation",
        "proves": "the historical clause, not today's",
        "body": {
            "question": "What are the payment terms for Sahyadri Agro Traders?",
            "as_of": "2025-01-15",
            "supplier_code": "SUP-01",
            "doc_types": ["contract"],
        },
        "expect_status": 200,
        "expect_outcome": "found",
        "expect_in_answer": "14",
    },
    {
        "name": "after it",
        "proves": "same question, same wording, different answer",
        "body": {
            "question": "What are the payment terms for Sahyadri Agro Traders?",
            "as_of": "2026-06-30",
            "supplier_code": "SUP-01",
            "doc_types": ["contract"],
        },
        "expect_status": 200,
        "expect_outcome": "found",
        "expect_in_answer": "30",
    },
    {
        "name": "inside a real coverage gap",
        "proves": "none_in_force is a third outcome, and costs no model call",
        "body": {
            "question": "What are the payment terms?",
            "as_of": "2025-11-15",
            "supplier_code": "SUP-06",
            "doc_types": ["contract"],
        },
        "expect_status": 200,
        "expect_outcome": "none_in_force",
    },
    {
        "name": "a clerk with no store",
        "proves": "rule 5 refuses at the boundary rather than returning nothing",
        "body": {
            "question": "payment terms?",
            "as_of": "2025-01-15",
            "role": "clerk",
        },
        "expect_status": 422,
    },
    {
        "name": "a date demo mode has not recorded",
        "proves": "no nearest-date fallback — that would contradict the beat",
        "body": {
            "question": "What are the payment terms for Sahyadri Agro Traders?",
            "as_of": "2025-03-01",
            "supplier_code": "SUP-01",
        },
        "expect_status": 404,
    },
]


def post(url: str, body: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=WEB, help="the WEB origin, not the API's")
    args = parser.parse_args(argv)

    print(f"through {args.base} — the proxy path a browser uses, not the API directly")
    print()

    failures = 0

    try:
        with urllib.request.urlopen(
            f"{args.base}/api/demo/document-questions", timeout=60
        ) as response:
            catalogue = json.loads(response.read())
    except Exception as exc:
        print(f"  FAIL  catalogue unreachable: {exc}")
        print("\n  Run `make serve` and `make web` first.")
        return 1

    ok = len(catalogue) >= 3
    mark = "ok  " if ok else "FAIL"
    print(f"  {mark}  catalogue — {len(catalogue)} question/date pairs")
    failures += 0 if ok else 1

    for case in CASES:
        status, payload = post(f"{args.base}/api/ask", case["body"])
        problems = []
        if status != case["expect_status"]:
            problems.append(f"status {status}, wanted {case['expect_status']}")
        if (
            "expect_outcome" in case
            and payload.get("outcome") != case["expect_outcome"]
        ):
            problems.append(f"outcome {payload.get('outcome')!r}")
        if "expect_in_answer" in case:
            answer = payload.get("answer") or ""
            if case["expect_in_answer"] not in answer:
                problems.append(f"answer does not state {case['expect_in_answer']}")
        if problems:
            failures += 1
            print(f"  FAIL  {case['name']} — {'; '.join(problems)}")
        else:
            print(f"  ok    {case['name']:<32} {case['proves']}")

    print()
    if failures:
        print(f"{failures} check(s) failed")
        return 1
    print("both beats reachable through the web app's own request path.")
    print()
    print("NOT COVERED: React event wiring. A button whose onClick was never")
    print("attached passes this and passes CI. That needs a browser driving the")
    print("page, and nobody has done it — see docs/PROGRESS.md, named debt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
