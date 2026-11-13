"""The sleep test in plain Python. The SQL in sql/00_account_windows.sql does the same thing
at scale; tests/test_sleep.py proves the two agree.

An account is described by one 24-bit mask per active day: bit h is set if the account
sent at least one transaction in hour h (UTC) of that day.
"""
from . import config, contiguity

MASK_24 = (1 << 24) - 1
CRIT = contiguity.critical_gaps(config.ALPHA)


def union(day_masks):
    out = 0
    for mask in day_masks:
        out |= mask
    return out


def longest_quiet(hour_mask: int):
    """Longest run of empty hours on the 24-hour clock. Returns (gap, midpoint hour)."""
    hours = [h for h in range(24) if (hour_mask >> h) & 1]
    if not hours:
        return 24, 0.0
    best_gap, best_start = -1, 0
    for i, h in enumerate(hours):
        nxt = hours[i + 1] if i + 1 < len(hours) else hours[0] + 24
        gap = nxt - h - 1
        if gap > best_gap:
            best_gap, best_start = gap, h
    mid = (best_start + 1 + best_gap / 2) % 24
    return best_gap, mid


def classify(day_masks, crit=None) -> dict:
    crit = crit if crit is not None else CRIT
    n_days = len(day_masks)
    hour_mask = union(day_masks)
    n_hours = bin(hour_mask).count("1")
    n_slots = sum(bin(m).count("1") for m in day_masks)
    gap, mid = longest_quiet(hour_mask)
    hours_per_day = n_slots / n_days if n_days else 0.0
    significant = gap >= config.MIN_GAP and gap >= crit[n_hours]
    if n_days < config.MIN_DAYS:
        label = "too_few"
    elif gap <= config.MACHINE_MAX_GAP and hours_per_day >= config.MACHINE_MIN_HOURS_PER_DAY:
        label = "machine"
    elif n_hours <= config.TIMER_MAX_HOURS:
        label = "timer"
    elif significant and gap <= config.MAX_GAP and n_hours >= config.MIN_HOURS:
        label = "sleeper"
    elif significant:
        label = "routine"
    else:
        label = "unclear"
    return {"class": label, "n_days": n_days, "n_hours": n_hours, "n_slots": n_slots, "gap": gap, "mid": mid,
            "hours_per_day": hours_per_day}


def rotate(mask: int, by: int) -> int:
    """Shift a day's activity around the clock, keeping its shape."""
    by %= 24
    return ((mask << by) | (mask >> (24 - by))) & MASK_24
