"""All choices the analysis depends on. Change a value here and re-run rebuild.py."""
import datetime as dt
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "out"
SQL = ROOT / "sql"
SITE = ROOT / "site"

SOURCE = "bigquery-public-data.crypto_near_mainnet_us"
DATASET = os.environ.get("BQ_DATASET", "proof_of_sleep")
LOCATION = "us-east1"   # where the NEAR public dataset physically lives


def project(required: bool = True) -> str:
    """The Google Cloud project that runs (and is billed for) the queries."""
    value = os.environ.get("BQ_PROJECT", "").strip()
    if not value:
        env = ROOT / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("BQ_PROJECT="):
                    value = line.split("=", 1)[1].strip()
    if not value:
        if not required:
            return "your-project"
        raise SystemExit("Set BQ_PROJECT in .env or the environment (see README).")
    return value


# ---- Sampling: the first 14 days of every month. Two full weeks, so every
# weekday appears exactly twice in every window.
WINDOW_DAYS = 14
FIRST_MONTH = (2021, 1)
LAST_MONTH = (2026, 10)


def month_starts():
    y, m = FIRST_MONTH
    while (y, m) <= LAST_MONTH:
        yield dt.date(y, m, 1)
        m += 1
        if m == 13:
            y, m = y + 1, 1


def window_filter(column: str = "block_date") -> str:
    """Literal date ranges, so BigQuery can prune partitions and bill only these days."""
    parts = []
    for start in month_starts():
        end = start + dt.timedelta(days=WINDOW_DAYS - 1)
        parts.append(f"({column} BETWEEN DATE '{start}' AND DATE '{end}')")
    return "\n    OR ".join(parts)


# ---- The sleep test. METHOD.md explains each value.
MIN_DAYS = 5                     # active on at least this many of the 14 days, or the account cannot be tested
MACHINE_MAX_GAP = 2              # never sleeps: no quiet stretch longer than this over the whole window...
MACHINE_MIN_HOURS_PER_DAY = 8    # ...and active in at least this many hours of a typical active day
TIMER_MAX_HOURS = 3              # on a timer: used this few hours of the clock or fewer
MIN_HOURS = 6                    # a sleeper uses at least this many different hours of the clock
MIN_GAP = 5                      # a sleeper's quiet stretch is at least this long
MAX_GAP = 14                     # and at most this long; longer means a narrow daily routine, not a day and a night
ALPHA = 0.05                     # the quiet stretch must be this unlikely if the hours used were random

# The midpoint of a person's sleep is usually close to 03:30 local time.
TYPICAL_SLEEP_MIDPOINT_LOCAL = 3.5

RELAYED_WINDOWS = ["2026-04-01", "2026-10-01"]              # windows for the people-behind-relayers check
APP_WINDOWS = ["2026-01-01", "2026-07-01", "2026-10-01"]    # windows where we also read which contract was called

BYTES_LIMIT_MAIN = 130_000_000_000   # refuses to run the big scan above this
BYTES_LIMIT_SMALL = 40_000_000_000   # refuses to run any other query above this
