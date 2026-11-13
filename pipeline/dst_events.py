"""Daylight-saving clock changes used as a natural experiment.

A person keeps to local time, so when their clocks change, their activity moves by one
hour in UTC. A machine on a UTC schedule does not move. Places without daylight saving
(most of Asia) do not move either, so they serve as a control group.

Each event compares the 14 days before the change with the 14 days after it. The change
day itself is excluded. Direction: autumn clocks go back, so local activity lands one hour
LATER in UTC (+1). Spring clocks go forward, so it lands one hour EARLIER (-1).
"""
import datetime as dt

# name, date of the clock change, direction of the UTC shift, region the change applies to
EVENTS = [
    ("eu_spring_2026", "2026-03-29", -1, "europe"),
    ("us_spring_2026", "2026-03-08", -1, "americas"),
    ("eu_autumn_2026", "2026-10-25", +1, "europe"),
    ("us_autumn_2026", "2026-11-01", +1, "americas"),
    # Placebos: ordinary dates with no clock change anywhere. Any "shift" here is noise.
    ("placebo_2026_05", "2026-05-17", 0, "none"),
    ("placebo_2026_06", "2026-06-14", 0, "none"),
    ("placebo_2026_07", "2026-07-12", 0, "none"),
    ("placebo_2026_08", "2026-08-16", 0, "none"),
]
DAYS_EACH_SIDE = 14
# 2026-11-01 only has 8 complete days of data after it at build time.
LAST_COMPLETE_DAY = "2026-11-08"


def windows(change: str):
    day = dt.date.fromisoformat(change)
    pre_start = day - dt.timedelta(days=DAYS_EACH_SIDE)
    pre_end = day - dt.timedelta(days=1)
    post_start = day + dt.timedelta(days=1)
    post_end = min(day + dt.timedelta(days=DAYS_EACH_SIDE), dt.date.fromisoformat(LAST_COMPLETE_DAY))
    return pre_start, pre_end, post_start, post_end


def values_sql() -> str:
    """Inline table of events for the SQL."""
    rows = []
    for name, change, direction, region in EVENTS:
        pre_start, pre_end, post_start, post_end = windows(change)
        rows.append(
            f"STRUCT('{name}' AS event, DATE '{change}' AS change_day, {direction} AS direction, '{region}' AS region,"
            f" DATE '{pre_start}' AS pre_start, DATE '{pre_end}' AS pre_end,"
            f" DATE '{post_start}' AS post_start, DATE '{post_end}' AS post_end)"
        )
    return "[\n    " + ",\n    ".join(rows) + "\n  ]"


def date_filter(column: str = "block_date") -> str:
    """Literal date ranges so partition pruning applies. Overlapping ranges are merged."""
    ranges = []
    for _, change, _, _ in EVENTS:
        pre_start, _, _, post_end = windows(change)
        ranges.append((pre_start, post_end))
    ranges.sort()
    merged = [list(ranges[0])]
    for start, end in ranges[1:]:
        if start <= merged[-1][1] + dt.timedelta(days=1):
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return "\n    OR ".join(f"({column} BETWEEN DATE '{a}' AND DATE '{b}')" for a, b in merged)
