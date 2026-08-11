"""How close two values have to be to mean the same thing.

**Tolerance is absolute, never relative.** The returns trap in this eval set is
a 0.3% gap — 54,759 gross units against 54,594 net — and any relative tolerance
loose enough to be useful would swallow it whole, making the trap unscoreable
and reporting a pass on the exact failure it exists to catch.

    counts, quantities, ids     exact
    money                       +/- 0.01   (matches corpus/README.md)
    rates, percentages          +/- 0.005

Kind comes from the reference column's name, which is available because the
expectation records its columns alongside its rows.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from enum import StrEnum

MONEY = Decimal("0.01")
RATE = Decimal("0.005")
EXACT = Decimal("0")


class Kind(StrEnum):
    EXACT = "exact"
    MONEY = "money"
    RATE = "rate"
    TEXT = "text"
    DATE = "date"


TOLERANCE = {Kind.EXACT: EXACT, Kind.MONEY: MONEY, Kind.RATE: RATE}

# Substrings, checked against the reference column name. Rates are tested
# first: `margin_pct` is a rate even though `margin` alone is money.
_RATE_HINTS = (
    "pct",
    "percent",
    "_rate",
    "rate_",
    "ratio",
    "uplift",
    "per_day",
    "days_of_cover",
    "variance",
    "f1",
    "share",
)
_MONEY_HINTS = (
    "revenue",
    "cost",
    "price",
    "value",
    "total",
    "subtotal",
    "margin",
    "cogs",
    "spend",
    "takings",
    "tax",
    "gst",
    "ordered",
    "basket",
)

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def as_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def classify(column: str, value: object) -> Kind:
    if value is None:
        return Kind.TEXT
    if isinstance(value, str) and _ISO_DATE.match(value):
        return Kind.DATE
    if as_decimal(value) is None:
        return Kind.TEXT

    name = (column or "").lower()
    if any(hint in name for hint in _RATE_HINTS):
        return Kind.RATE
    if any(hint in name for hint in _MONEY_HINTS):
        return Kind.MONEY
    return Kind.EXACT


def _places(value: Decimal) -> int:
    exponent = value.as_tuple().exponent
    return -exponent if isinstance(exponent, int) and exponent < 0 else 0


def numbers_match(want: Decimal, got: Decimal, kind: Kind) -> bool:
    """Do these two numbers state the same quantity?

    Compared at the COARSER of the two precisions, because that is the real
    under-determination: "rank the days by average takings" does not say how
    many decimals. A reference writing `round(avg(...))` gives 326958 where a
    model's raw average gives 326958.0876 — the same answer, and absolute money
    tolerance alone would call it wrong.

    **Compared on the raw difference against half a unit of that precision, and
    never by re-rounding.** Re-rounding double-rounds, twice over in practice:

    * q031's reference reports `11.5` at one decimal and the model reports
      `11.55` at two, both from a true 11.549. Quantizing 11.55 back to one
      decimal gives 11.6 and scores a correct answer wrong.
    * Postgres rounds half away from zero, Python's `Decimal.quantize` rounds
      half to even, and they disagree on exact halves — which is where money
      lands. `sum(line_total)::bigint` gives 34709 for 34708.50 where quantize
      gives 34708. Four of q035's campaigns sit on an exact half.

    A value stated to `places` decimals stands for anything within half a unit
    of it, so that is what is allowed, plus the kind's own tolerance. This
    fixes a boundary; it does not open a gap. Aligning decimals is not aligning
    significant figures, so a model answering 1200 where the truth is 1234.56
    still fails at zero places.
    """
    places = min(_places(want), _places(got))
    half_a_unit = Decimal(1).scaleb(-places) / 2
    return abs(want - got) <= half_a_unit + TOLERANCE[kind]


def values_match(want: object, got: object, kind: Kind) -> bool:
    if want is None or got is None:
        return want is None and got is None

    if kind is Kind.TEXT:
        return _text(want) == _text(got)

    if kind is Kind.DATE:
        # A date, a timestamptz and a rendered string all describe the same
        # day; only the day is being asked about.
        return _day(want) == _day(got)

    left, right = as_decimal(want), as_decimal(got)
    if left is None or right is None:
        return _text(want) == _text(got)
    return numbers_match(left, right, kind)


def _text(value: object) -> str:
    """Booleans, padded to_char output and case all normalise away."""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip().casefold()
    return {"t": "true", "f": "false"}.get(text, text)


def _day(value: object) -> str:
    text = str(value).strip()
    return text.split("T")[0].split(" ")[0]
