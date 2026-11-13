#!/usr/bin/env python3
"""One command that rebuilds every chart, number and document.

  python rebuild.py                   from data/raw: seconds, no network, no keys, no packages
  python rebuild.py --check           same, and verifies the published hash of the results
  python rebuild.py --from-bigquery   first re-pull data/raw from BigQuery and the public APIs
"""
import argparse
import hashlib
import json
import sys

from pipeline import analyze, build_site, config, pull_bigquery, pull_public, render_docs

HASH_FILE = config.OUT / "results.sha256"


def results_hash() -> str:
    return hashlib.sha256((config.OUT / "results.json").read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from-bigquery", action="store_true", help="re-pull data/raw first")
    parser.add_argument("--check", action="store_true", help="fail if the results differ from the published hash")
    parser.add_argument("--write-hash", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.from_bigquery:
        sys.argv = ["pull_bigquery"]
        pull_bigquery.main()
        pull_public.main()

    results = analyze.main()
    build_site.main()
    render_docs.render_docs()
    sys.path.insert(0, str(config.ROOT / "video"))
    import script as demo_script          # writes docs/DEMO_SCRIPT.md from the same numbers
    demo_script.write_markdown(demo_script.script())

    h = results["headline"]
    print(f"accounts {h['accounts']:,}")
    print(f"people {h['humans']:,}")
    print(f"machines {h['machines']:,}")
    print(f"machine share of transactions {h['machine_tx_share'] * 100:.1f}%")
    print(f"decline from peak {h['decline_from_peak'] * 100:.1f}%")
    print("charts site/index.html")

    digest = results_hash()
    print(f"sha256 of data/out/results.json: {digest}")
    if args.write_hash:
        HASH_FILE.write_text(digest + "\n", encoding="utf-8", newline="\n")
    if args.check:
        expected = HASH_FILE.read_text(encoding="utf-8").strip()
        if digest == expected:
            print("MATCH: results reproduce the published hash")
        else:
            print(f"MISMATCH: published hash is {expected}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
