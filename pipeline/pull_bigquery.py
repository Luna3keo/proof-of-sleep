"""Rebuild data/raw from the NEAR BigQuery public dataset.

  python -m pipeline.pull_bigquery             # everything (about 150 GB of free-tier quota)
  python -m pipeline.pull_bigquery --step 00   # one step only
  python -m pipeline.pull_bigquery --plan      # dry-run: print the bytes each step would read
  python -m pipeline.pull_bigquery --print 10  # print one step's exact SQL, ready to paste

Every query filters on block_date with literal dates, so BigQuery reads only the sampled days.
"""
import argparse
import csv
import datetime as dt
import sys

from . import bq, config, contiguity, dst_events, pull_verified


def crit_array(alpha) -> str:
    return "[" + ",".join(str(v) for v in contiguity.critical_gaps(alpha)) + "]"


def class_case(gap="gap", hours="n_hours", days="n_days", slots="n_slots") -> str:
    """The classification rules as SQL, identical to pipeline/sleep.py."""
    crit = crit_array(config.ALPHA)
    significant = f"{gap} >= {config.MIN_GAP} AND {gap} >= {crit}[OFFSET({hours})]"
    return (
        "CASE\n"
        f"      WHEN {days} < {config.MIN_DAYS} THEN 'too_few'\n"
        f"      WHEN {gap} <= {config.MACHINE_MAX_GAP} AND {slots} / {days} >= {config.MACHINE_MIN_HOURS_PER_DAY} THEN 'machine'\n"
        f"      WHEN {hours} <= {config.TIMER_MAX_HOURS} THEN 'timer'\n"
        f"      WHEN {significant} AND {gap} <= {config.MAX_GAP} AND {hours} >= {config.MIN_HOURS} THEN 'sleeper'\n"
        f"      WHEN {significant} THEN 'routine'\n"
        "      ELSE 'unclear'\n"
        "    END"
    )


def params(required: bool = True) -> dict:
    return dict(
        project=config.project(required), dataset=config.DATASET, source=config.SOURCE,
        window_filter=config.window_filter(), min_days=config.MIN_DAYS,
        class_case=class_case(), class_case_inline=class_case(gap="g.gap", hours="ARRAY_LENGTH(hs)"),
        crit_05=crit_array(0.05), crit_01=crit_array(0.01),
    )


def render(name: str, required: bool = True, **extra) -> str:
    text = (config.SQL / name).read_text(encoding="utf-8")
    return text.format(**{**params(required), **extra})


def save(name: str, rows):
    config.RAW.mkdir(parents=True, exist_ok=True)
    path = config.RAW / name
    if not rows:
        raise SystemExit(f"{name}: query returned no rows")
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    bq.log(f"  wrote {path.name}: {len(rows)} rows")


def window_list(starts) -> str:
    parts = []
    for start in starts:
        end = dt.date.fromisoformat(start) + dt.timedelta(days=config.WINDOW_DAYS - 1)
        parts.append(f"(block_date BETWEEN DATE '{start}' AND DATE '{end}')")
    return "\n    OR ".join(parts)


def verified_params() -> dict:
    names = pull_verified.load()
    config.RAW.mkdir(parents=True, exist_ok=True)
    (config.RAW / "verified_meta.csv").write_text(f"accounts\n{len(names)}\n", encoding="utf-8", newline="\n")
    return {"verified_list": "[" + ",".join("'" + n.replace("'", "") + "'" for n in names) + "]", "verified_count": len(names)}


def steps():
    """(step id, sql file, output csv or None, byte cap, function giving extra template values)"""
    small = config.BYTES_LIMIT_SMALL
    return [
        ("00", "00_account_windows.sql", None, config.BYTES_LIMIT_MAIN, dict),
        ("01", "01_classes.sql", "classes.csv", small, dict),
        ("02", "02_clock.sql", "clock.csv", small, dict),
        ("03", "03_gaps.sql", "gaps.csv", small, dict),
        ("04", "04_timezones.sql", "timezones.csv", small, dict),
        ("05", "05_retention.sql", "retention.csv", small, dict),
        ("06", "06_sensitivity.sql", "sensitivity.csv", small, dict),
        ("07", "07_concentration.sql", "concentration.csv", small, dict),
        ("08", "08_dst.sql", "dst.csv", small, lambda: {"dst_sql": dst_events.values_sql(), "dst_filter": dst_events.date_filter()}),
        ("09", "09_apps.sql", "apps.csv", small, lambda: {"app_filter": window_list(config.APP_WINDOWS)}),
        ("10", "10_daily_totals.sql", "daily_totals.csv", small, dict),
        ("11", "11_families.sql", "families.csv", small, dict),
        ("12", "12_relayed.sql", "relayed.csv", small,
         lambda: {"relayed_filter": window_list(config.RELAYED_WINDOWS), "relayed_windows": ", ".join(config.RELAYED_WINDOWS)}),
        ("15", "15_calibration.sql", "calibration_masks.csv", small, dict),
        ("16", "16_verified.sql", "verified.csv", small, verified_params),
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", help="run one step, e.g. 00")
    parser.add_argument("--plan", action="store_true", help="dry-run only")
    parser.add_argument("--print", dest="print_step", help="print one step's SQL and stop")
    args = parser.parse_args()

    if args.print_step:
        for num, sql_file, _, _, extra in steps():
            if num == args.print_step:
                print(render(sql_file, required=False, **extra()))
                return
        raise SystemExit(f"No step {args.print_step}")

    bq.query(f"CREATE SCHEMA IF NOT EXISTS `{config.project()}.{config.DATASET}` "
             f"OPTIONS(location='{config.LOCATION}', default_table_expiration_days=60)", 1_000_000)

    total = 0
    plan_rows = []
    complete = True
    for num, sql_file, csv_name, cap, extra in steps():
        if args.step and args.step != num:
            continue
        sql = render(sql_file, **extra())
        if args.plan:
            try:
                planned = bq.dry_run(sql)
            except SystemExit as err:
                print(num, sql_file, "cannot plan until step 00 has run:", str(err).splitlines()[0][:100])
                complete = False
                continue
            total += planned
            plan_rows.append([num, sql_file, f"{planned/1e9:.2f}"])
            print(f"{num} {sql_file:32s} {planned/1e9:8.2f} GB")
            continue
        bq.log(f"step {num}: {sql_file}")
        if num == "00":     # a table cannot be replaced by one with a different layout
            bq.query(f"DROP TABLE IF EXISTS `{config.project()}.{config.DATASET}.account_windows`", 1_000_000)
        rows, used = bq.query(sql, cap)
        total += used
        bq.log(f"  read {used/1e9:.2f} GB")
        if csv_name:
            save(csv_name, rows)
    if args.plan and not args.step and complete:
        with open(config.RAW / "scan_plan.csv", "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["step", "sql_file", "gb"])
            writer.writerows(plan_rows)
    print(f"total {total/1e9:.1f} GB", file=sys.stderr)


if __name__ == "__main__":
    main()
