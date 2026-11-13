"""How long a quiet stretch must be before it is more than chance.

Suppose an account used `m` different hours of the 24-hour clock, and suppose the hours
it used were random. The hours it did not use would then be scattered around the clock,
and a long unbroken quiet stretch would be rare. This module computes that chance exactly
(no simulation), and the shortest quiet stretch that is unlikely enough.

Counting: place m used hours on a circle of 24. The number of arrangements whose longest
quiet run is below g is (24/m) x (ways to split the 24-m quiet hours into m gaps, each
shorter than g). Dividing by C(24, m) gives the probability.
"""
import math
from functools import lru_cache

HOURS = 24


@lru_cache(maxsize=None)
def _splits(total: int, parts: int, largest: int) -> int:
    """Ways to write `total` as an ordered sum of `parts` integers, each from 0 to `largest`."""
    ways = [1] + [0] * total
    for _ in range(parts):
        updated = [0] * (total + 1)
        for used in range(total + 1):
            if ways[used]:
                for piece in range(0, min(largest, total - used) + 1):
                    updated[used + piece] += ways[used]
        ways = updated
    return ways[total]


def p_quiet_at_least(m: int, gap: int) -> float:
    """Chance that m random hours leave a quiet stretch of at least `gap` hours."""
    if m <= 0 or gap <= 0:
        return 1.0
    if gap > HOURS - m:
        return 0.0
    below = _splits(HOURS - m, m, gap - 1) * HOURS // m
    return 1 - below / math.comb(HOURS, m)


def critical_gaps(alpha: float):
    """For each number of used hours (index 0 to 24), the shortest quiet stretch that passes.
    99 means no stretch can pass at that many used hours."""
    out = []
    for m in range(HOURS + 1):
        passing = [g for g in range(1, HOURS + 1) if p_quiet_at_least(m, g) <= alpha and g <= HOURS - m]
        out.append(passing[0] if passing and m > 0 else 99)
    return out
