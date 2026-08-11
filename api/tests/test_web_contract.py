"""The web client's types are hand-written. This is what keeps them honest.

`CONVENTIONS.md` says to generate `web/lib/api.ts` from the OpenAPI schema rather
than hand-writing the types twice, and it is hand-written anyway. Generating it
means adding an npm dependency and a codegen step, which is a decision to take
deliberately rather than in passing — so until then, the drift the convention
worries about is caught here instead.

`api/` is the only boundary between the two apps, and a field added on this side
and missed on that one shows up as `undefined` in a table cell rather than as an
error. That is the whole failure mode, and it is cheap to close.

The parsing is deliberately narrow: one `export type` block, field names only, no
attempt to compare TypeScript types against JSON Schema types. A checker that
tried to do more here would be guessing at structure, which is how this project
has been bitten before.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pos_copilot.app import app

WEB_CLIENT = Path(__file__).resolve().parents[2] / "web" / "lib" / "api.ts"


def ts_fields(source: str, type_name: str) -> set[str]:
    """Field names declared in `export type <type_name> = { ... }`."""
    match = re.search(rf"export type {type_name} = \{{(.*?)\n\}};", source, re.S)
    if not match:
        raise AssertionError(f"no `export type {type_name}` block in api.ts")
    return set(re.findall(r"^\s{2}(\w+)\??:", match.group(1), re.M))


@pytest.mark.parametrize(
    ("ts_type", "schema_name"),
    [("QueryResponse", "QueryResponse"), ("Answer", "Answer")],
)
def test_the_web_client_mirrors_the_api_exactly(ts_type, schema_name):
    if not WEB_CLIENT.exists():
        pytest.skip("web/lib/api.ts is not present")
    declared = ts_fields(WEB_CLIENT.read_text(encoding="utf-8"), ts_type)
    served = set(app.openapi()["components"]["schemas"][schema_name]["properties"])

    # Known-positive: a parser that silently matched nothing would pass every
    # comparison it was asked to make. A probe that cannot tell "found nothing"
    # from "looked at nothing" is instance eight of this project's defect class.
    assert len(declared) >= 3, (
        f"parsed too few fields from {ts_type} — check the parser, not the types"
    )

    assert declared == served, (
        f"{ts_type} and the API's {schema_name} have drifted.\n"
        f"  only in api.ts: {sorted(declared - served)}\n"
        f"  only in the API: {sorted(served - declared)}"
    )
