"""Reading configuration from the environment, where blank means unset.

`os.environ.get("X", default)` returns `""` for a variable that exists and is
empty, and `int("")` raises. That is not a theoretical case here:

- `.env.example` ships `GEMINI_API_KEY=` — a deliberately empty value, because
  demo mode needs no key.
- `export FOO` in the Makefile exports `FOO=` when `FOO` is not defined, so
  every optional setting arrives as an empty string rather than as absent.

So the default has to apply to blank as well as to missing, or a variable
nobody set takes down the request that reads it. These three functions are the
one place that rule lives.
"""

from __future__ import annotations

import os


def text(name: str, default: str = "") -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def integer(name: str, default: int) -> int:
    value = text(name)
    return int(value) if value else default


def number(name: str, default: float) -> float:
    value = text(name)
    return float(value) if value else default
