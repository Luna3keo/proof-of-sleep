"""Optional: daily NEAR Intents swap volume from the Intents Explorer API.

Needs a partner JWT in .env (INTENTS_JWT=...), from https://partners.near-intents.org.
The analysis does not depend on this: it uses DefiLlama's public volume series.

STATUS: not run against the live API, because this project has no partner token.
tests/test_explorer.py checks the paging and the daily totals against a fake server.

The API terms limit how long data may be kept, so raw rows are never written to disk.
Only daily totals are saved, in data/raw/intents_explorer_daily.csv.

  python -m pipeline.pull_intents_explorer 2026-10-01 2026-10-14
"""
import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request

from . import config

BASE_URL = os.environ.get("INTENTS_EXPLORER_URL", "https://explorer.near-intents.org/api/v0/transactions")
PAGE_SIZE = 1000
SECONDS_BETWEEN_REQUESTS = 5.2    # the API allows one request every 5 seconds per partner


def token() -> str:
    value = os.environ.get("INTENTS_JWT", "").strip()
    env = config.ROOT / ".env"
    if not value and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("INTENTS_JWT="):
                value = line.split("=", 1)[1].strip()
    if not value:
        raise SystemExit("Set INTENTS_JWT in .env. Get one at https://partners.near-intents.org.")
    return value


def get_page(params, jwt):
    url = BASE_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + jwt, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def day_totals(day: dt.date, jwt: str, pause: float = SECONDS_BETWEEN_REQUESTS):
    """Sum one UTC day. Raw rows stay in memory only, and only long enough to be added up."""
    start = int(dt.datetime(day.year, day.month, day.day, tzinfo=dt.timezone.utc).timestamp())
    params = {"numberOfTransactions": PAGE_SIZE, "statuses": "SUCCESS",
              "startTimestampUnix": start - 1, "endTimestampUnix": start + 86400, "direction": "next"}
    usd, swaps = 0.0, 0
    while True:
        rows = get_page(params, jwt)
        if not rows:
            break
        for row in rows:
            usd += float(row.get("amountInUsd") or 0)
            swaps += 1
        if len(rows) < PAGE_SIZE:
            break
        last = rows[-1]
        params["lastDepositAddress"] = last["depositAddress"]
        if last.get("depositMemo"):
            params["lastDepositMemo"] = last["depositMemo"]
        else:
            params.pop("lastDepositMemo", None)
        time.sleep(pause)
    return {"date": day.isoformat(), "swaps": swaps, "volume_usd": round(usd, 2)}


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    first, last = dt.date.fromisoformat(sys.argv[1]), dt.date.fromisoformat(sys.argv[2])
    jwt = token()
    rows = []
    day = first
    while day <= last:
        rows.append(day_totals(day, jwt))
        print(rows[-1], file=sys.stderr)
        day += dt.timedelta(days=1)
        time.sleep(SECONDS_BETWEEN_REQUESTS)
    path = config.RAW / "intents_explorer_daily.csv"
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "swaps", "volume_usd"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
