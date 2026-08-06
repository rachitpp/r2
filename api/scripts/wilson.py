"""Wilson score interval for a binomial proportion.

Every accuracy figure this project publishes carries n and an interval
(ADR-0001). The interval is computed here rather than quoted, so a number in
the README cannot drift from the sample it came from.

Wilson rather than the normal approximation: at n≈40 with p near 0.85 the
normal interval is visibly wrong — it can run past 1.0 and it degrades badly
whenever np or n(1-p) is small, which is exactly the regime a hallucination or
silent-wrong count lives in.

    >>> summarise(25, 30)
    '83.3% (25/30, 95% CI 66-93%)'

Stdlib only, like the seed generator.
"""

from __future__ import annotations

import math

# Two-sided 95%.
Z_95 = 1.959963984540054


def wilson(successes: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """Return (lower, upper) as proportions in [0, 1]."""
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= successes <= n:
        raise ValueError("successes must be between 0 and n")

    phat = successes / n
    denominator = 1 + z**2 / n
    centre = (phat + z**2 / (2 * n)) / denominator
    spread = z / denominator * math.sqrt(phat * (1 - phat) / n + z**2 / (4 * n**2))
    return max(0.0, centre - spread), min(1.0, centre + spread)


def summarise(successes: int, n: int, z: float = Z_95) -> str:
    """The one-line form every published accuracy figure uses."""
    low, high = wilson(successes, n, z)
    return (
        f"{100 * successes / n:.1f}% ({successes}/{n}, "
        f"95% CI {round(100 * low)}-{round(100 * high)}%)"
    )


def decides(successes: int, n: int, line: float, z: float = Z_95) -> str:
    """Whether the interval clears a threshold, or straddles it.

    Returns 'below', 'above', or 'inconclusive'. ADR-0001 threshold 2: act only
    when the interval excludes the line.
    """
    low, high = wilson(successes, n, z)
    if high < line:
        return "below"
    if low > line:
        return "above"
    return "inconclusive"


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("usage: wilson.py <successes> <n>")
        raise SystemExit(2)
    k, total = int(sys.argv[1]), int(sys.argv[2])
    print(summarise(k, total))
    print(f"against the 85% line: {decides(k, total, 0.85)}")
