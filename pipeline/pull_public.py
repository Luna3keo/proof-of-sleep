"""Public market and usage data that needs no account or key.

Writes CSV files to data/raw/. Each file is the source's own numbers, unmodified except
for keeping only the columns the analysis uses.

  python -m pipeline.pull_public
"""
import csv
import datetime as dt
import json
import sys
import urllib.request

from . import config

USER_AGENT = "proof-of-sleep-research/1.0"


def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def write(name, header, rows):
    path = config.RAW / name
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    print(f"  wrote {name}: {len(rows)} rows", file=sys.stderr)


def nearblocks_daily():
    """Daily chain totals and price, as published by NearBlocks."""
    charts = fetch_json("https://api.nearblocks.io/v1/charts")["charts"]
    header = ["date", "near_price", "market_cap", "total_supply_near", "txns", "txn_fee_near",
              "new_accounts", "active_accounts"]
    rows = []
    for c in sorted(charts, key=lambda x: x["date"]):
        rows.append([
            c["date"][:10],
            c["near_price"],
            c["market_cap"],
            f"{float(c['total_supply']) / 1e24:.2f}",
            c["txns"],
            f"{float(c['txn_fee']) / 1e24:.4f}",
            c["new_accounts"],
            c["active_accounts"],
        ])
    write("nearblocks_daily.csv", header, rows)


def _llama(path: str):
    out = []
    data = fetch_json("https://api.llama.fi/" + path)
    for stamp, value in data.get("totalDataChart") or []:
        out.append((dt.datetime.fromtimestamp(stamp, dt.timezone.utc).date().isoformat(), value))
    return out


def defillama():
    """NEAR Intents volume and fees, and NEAR's own chain fees, as tracked by DefiLlama."""
    series = {
        "intents_volume_usd": "summary/dexs/near-intents?dataType=dailyVolume",
        "intents_fees_usd": "summary/fees/near-intents?dataType=dailyFees",
        "chain_fees_usd": "summary/fees/near?dataType=dailyFees",
    }
    table = {}
    for column, path in series.items():
        for day, value in _llama(path):
            table.setdefault(day, {})[column] = value
    columns = list(series)
    rows = [[day] + [table[day].get(c, "") for c in columns] for day in sorted(table)]
    write("defillama_daily.csv", ["date"] + columns, rows)


def main():
    config.RAW.mkdir(parents=True, exist_ok=True)
    nearblocks_daily()
    defillama()


if __name__ == "__main__":
    main()
