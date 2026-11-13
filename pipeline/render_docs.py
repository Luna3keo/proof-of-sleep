"""Fills the document templates in docs/templates/ with numbers from results.json."""
import csv
import json
import re
import statistics as st

from . import charts as C
from . import config
from .charts import full, pct

UNITS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
         "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def words(n: int) -> str:
    """Spell a number, so the voice reads the exact value."""
    if n < 20:
        return UNITS[n]
    if n < 100:
        return TENS[n // 10] + ("-" + UNITS[n % 10] if n % 10 else "")
    if n < 1000:
        return UNITS[n // 100] + " hundred" + (" " + words(n % 100) if n % 100 else "")
    if n < 1_000_000:
        return words(n // 1000) + " thousand" + (" " + words(n % 1000) if n % 1000 else "")
    return words(n // 1_000_000) + " million" + (" " + words(n % 1_000_000) if n % 1_000_000 else "")


def month_year(window) -> str:
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
              "November", "December"]
    year, month, _ = window.split("-")
    return f"{months[int(month) - 1]} {year}"


def scan_sizes():
    path = config.RAW / "scan_plan.csv"
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return {r["step"]: float(r["gb"]) for r in rows}


def flag_list(flagged) -> str:
    grouped = {}
    for f in flagged:
        grouped.setdefault(f["family"], []).append(C.month_label(f["window"]))
    return "; ".join(f"`{family}` ({', '.join(months)})" for family, months in grouped.items())


def values(R) -> dict:
    h = R["headline"]
    W = {w["window"]: w for w in R["windows"]}
    last = W[h["latest_window"]]
    cal, cross, dst, ret, ll, t, sens, ver, est = (R["calibration"], R["crosscheck"], R["dst"], R["retention"]["since_2025"], R["lead_lag"],
                                                   R["trend"], R["sensitivity"], R["verified"], R["people_estimate"])
    rel = R["relayed"][h["latest_window"]]
    intents = R["intents"]
    apps = R["apps"]
    con = R["concentration"][-1]
    scans = scan_sizes()
    extra = rel["relayed_sleepers_not_counted_as_signers"]
    intents_row = next(r for r in apps["latest_top_by_txs"] if r["contract"] == "intents.near")
    first = W["2025-01-01"]
    needed_25k = (25000 / t["latest"]) ** (1 / 60) - 1
    gap_real = max(range(24), key=lambda i: cal["gap_real"][i])
    gap_null = max(range(24), key=lambda i: cal["gap_null"][i])
    gap_ver = max(range(24), key=lambda i: ver["gap_hist"][i])
    worst = cross["worst_ratio"]
    flagged = R["flagged_programs"]
    sens_keys = [k for k in sens if k not in ("base", "no_chance_test")]
    sens_vals = [sens[k]["versus_base"] for k in sens_keys]
    round100 = lambda x: full(round(x, -2))  # noqa: E731
    v = {
        "latest_label": h["latest_label"],
        "accounts": full(h["accounts"]),
        "light": full(h["light_accounts"]),
        "light_prev": full(h["light_accounts_prev"]),
        "regular": full(h["regular_accounts"]),
        "humans": full(h["humans"]),
        "typical_per_100": f"{h['typical_people_per_100']:.0f}",
        "people_low": round100(h["estimated_people_low"]),
        "people_high": round100(h["estimated_people_high"]),
        "pass_share": pct(est["pass_share"], 1),
        "decline_adjusted": f"{h['decline_adjusted'] * 100:.0f}",
        "ver_recent": pct(ver["recent_pass_rate"], 0),
        "ver_2023": pct(ver["by_year"]["2023"]["pass_rate"], 0),
        "ver_2024": pct(ver["by_year"]["2024"]["pass_rate"], 0),
        "ver_2026": pct(ver["by_year"]["2026"]["pass_rate"], 0),
        "ret12_recent_sleeper": pct(st.mean(c["sleeper"] for c in R["retention"]["last_three_12m_cohorts"]), 0),
        "ret12_recent_machine": pct(st.mean(c["machine"] for c in R["retention"]["last_three_12m_cohorts"]), 0),
        "lead_chance": f"{ll['chance_of_this_many'] * 100:.0f}%",
        "lead_list": lead_list(ll),
        "machine_tx_share": pct(h["machine_tx_share"], 0),
        "machines": full(h["machines"]),
        "top100_machines": str(con["top100_machines"]),
        "top100_sleepers": str(con["top100_sleepers"]),
        "top100_share": pct(con["top_100"], 0),
        "delegated_share": pct(rel["delegate_actions_non_machine"] / last["txs"], 0),
        "game_share": pct(apps["game_sleepers"] / h["sleepers"], 0),
        "telegram_share": pct(h["telegram_share"], 0),
        "named": full(h["humans_named"]),
        "peak_month": month_year(h["peak_window"]),
        "peak_humans": full(h["peak_humans"]),
        "decline": f"{h['decline_from_peak'] * 100:.0f}",
        "intents_first": "$" + C.compact(first["intents_usd"]),
        "intents_last": "$" + C.compact(last["intents_usd"]),
        "humans_vs_headline_r": f"{ll['humans_vs_headline_r']:.2f}",
        "trend_fall": pct(abs(t["monthly_change"])),
        "half_life": f"{t['half_life_months']:.0f}",
        "ret12_sleeper": pct(ret["sleeper"]["12"], 0),
        "ret12_machine": pct(ret["machine"]["12"], 0),
        "intents_machine_share": pct(intents_row["machine_txs"] / intents_row["txs"], 0),
        "intents_txs": full(intents_row["txs"]),
        "ver_accounts": full(ver["verified_accounts"]),
        "ver_n": full(ver["account_windows"]),
        "ver_pass": pct(ver["pass_rate"], 0),
        "ver_base": pct(ver["same_windows_all_accounts_pass_rate"], 0),
        "ver_routine": pct(ver["routine_rate"], 0),
        "ver_machine": pct(ver["machine_rate"], 0),
        "lift": f"{ver['lift']:.1f}",
        "fpr": pct(cal["false_positive_rate"], 1),
        "real_rate": pct(cal["real_sleeper_rate"], 0),
        "false_share": pct(cal["expected_false_share_of_sleepers"], 0),
        "gap_real": str(gap_real),
        "gap_null": str(gap_null),
        "gap_ver": str(gap_ver),
        "cross_windows": f"{cross['windows_within_1pct']} of {cross['windows_compared']} windows",
        "cross_days": f"{cross['daily_tx_within_1pct']} of {cross['daily_days']} days",
        "cross_acct_days": f"{cross['daily_acct_within_1pct']} of {cross['daily_days']} days",
        "cross_day_count": str(cross["daily_days"]),
        "worst_ratio": f"{worst['ratio']:.4f} ({C.month_label(worst['window'])})",
        "relayed_extra": full(extra),
        "relayed_only": full(rel["relayed_only_sleepers"]),
        "relayed_extra_pct": f"+{extra / h['humans'] * 100:.0f}%",
        "min_days": str(config.MIN_DAYS),
        "dst_events": str(dst["n_events"]),
        "dst_effect": f"{dst['mean_signed_effect']:+.2f}",
        "dst_low": f"{dst['ci_low']:+.2f}",
        "dst_high": f"{dst['ci_high']:+.2f}",
        "lead_humans_r": f"{ll['best_lead_humans']['r']:+.2f}",
        "lead_humans_p": f"{ll['best_lead_humans']['p']:.2f}",
        "lead_sig": str(ll["significant_count"]),
        "lead_n": str(ll["n_tests"]),
        "lead_expected": f"{ll['n_tests'] * 0.05:.1f}",
        "price_low": f"${intents['price_low']:.2f}",
        "price_low_month": month_year(intents["price_low_window"]),
        "projected_12m": full(t["projected_12m"]),
        "needed_peak": f"{t['growth_needed_to_regain_peak_in_5y'] * 100:+.1f}%",
        "needed_25k": f"{needed_25k * 100:+.1f}%",
        "window_count": str(len(R["windows"])),
        "main_scan_gb": f"{scans['00']:.0f}",
        "total_scan_gb": f"{sum(scans.values()):.0f}",
        "alpha": str(config.ALPHA),
        "machine_max_gap": str(config.MACHINE_MAX_GAP),
        "machine_min_hours": str(config.MACHINE_MIN_HOURS_PER_DAY),
        "timer_max": str(config.TIMER_MAX_HOURS),
        "min_hours": str(config.MIN_HOURS),
        "min_gap": str(config.MIN_GAP),
        "max_gap": str(config.MAX_GAP),
        "flag_min": full(1000),
        "flag_share": "50%",
        "flag_count": str(len(flagged)),
        "flag_list": flag_list(flagged),
        "calib_n": full(cal["accounts"]),
        "calib_window": "1-14 October 2026",
        "sens_range": f"{min(sens_vals) * 100:+.0f}% to {max(sens_vals) * 100:+.0f}%",
        "sens_no_chance": f"{sens['no_chance_test']['count'] / h['humans']:.1f}",
    }
    return v


def lead_list(ll) -> str:
    names = {"humans": "the number passing", "headline_accounts": "active accounts", "txs": "transactions", "intents_volume": "Intents volume"}
    def when(lag):
        if lag == 0:
            return "in the same month as price"
        return f"{abs(lag)} month{'s' if abs(lag) != 1 else ''} {'before' if lag > 0 else 'after'} price"
    return "; ".join(f"{names[t['signal']]} {when(t['lag_months'])} (r = {t['r']:+.2f})" for t in ll["significant_tests"])


def x_length(text: str) -> int:
    """X counts every URL as 23 characters."""
    return len(re.sub(r"https?://\S+", "x" * 23, text))


def links():
    return json.loads((config.ROOT / "data" / "links.json").read_text(encoding="utf-8"))


TWEET_DRAFTS = [
    "How many NEAR accounts are people? We checked who sleeps: of {accounts} active in two weeks, {humans} do. "
    "{machines} never sleep and sent {machine_tx_share} of transactions.\n\n"
    "Built at NEAR HACKATHON @NEARProtocol #NEARHackathon\n\nDoes yours sleep? {site}\nCode: {repo}",
    "How many NEAR accounts are people? We checked who sleeps: of {accounts} active in two weeks, {humans} do.\n\n"
    "Built at NEAR HACKATHON @NEARProtocol #NEARHackathon\n\nDoes yours sleep? {site}\nCode: {repo}",
]


def social(v, video_seconds="(not recorded yet)"):
    L = links()
    for draft in TWEET_DRAFTS:                       # the first draft that fits in one tweet
        main = draft.format(site=L["site"], repo=L["repo"], **v)
        if x_length(main) <= 280:
            break
    else:
        raise SystemExit("No tweet draft fits in 280 characters")
    v.update(x_main=main, x_main_len=str(x_length(main)), video_seconds=video_seconds, repo_url=L["repo"], site_url=L["site"])
    idea = (f"NEAR's active-account and transaction counts are often read as proof of real demand, but nobody can say how many of those accounts are people. "
            f"Proof of Sleep tests every account's daily rhythm on public NEAR data, because people sleep and machines do not, and it checks the test against "
            f"{v['ver_accounts']} NEAR accounts verified as human by a face scan. "
            f"Of {v['accounts']} accounts active in two weeks of October 2026, {v['humans']} pass, and {v['machines']} accounts that never sleep sent {v['machine_tx_share']} of all transactions. "
            f"The result is an investment thesis with its evidence for and against, a dashboard that shows every chart's query, a live check of any NEAR account, and one command that rebuilds every number. "
            f"NEAR makes this possible because every account's full history is public in its BigQuery dataset, and its on-chain I-Am-Human registry gives real people to test against.")
    v.update(idea=idea, idea_len=str(len(idea)))
    return v


def fill(template: str, v: dict) -> str:
    missing = sorted(set(re.findall(r"{{(\w+)}}", template)) - set(v))
    if missing:
        raise SystemExit("Template placeholders with no value: " + ", ".join(missing))
    return re.sub(r"{{(\w+)}}", lambda m: v[m.group(1)], template)


def render_docs():
    R = json.loads((config.OUT / "results.json").read_text(encoding="utf-8"))
    length_file = config.OUT / "video_seconds.txt"
    video_seconds = length_file.read_text(encoding="utf-8").strip() if length_file.exists() else "(not recorded yet)"
    v = social(values(R), video_seconds)
    tpl = config.ROOT / "docs" / "templates"
    targets = {"THESIS.in.md": config.ROOT / "THESIS.md", "METHOD.in.md": config.ROOT / "METHOD.md",
               "README.in.md": config.ROOT / "README.md", "X_POST.in.md": config.ROOT / "docs" / "X_POST.md",
               "SUBMISSION.in.md": config.ROOT / "docs" / "SUBMISSION.md"}
    for name, out in targets.items():
        out.write_text(fill((tpl / name).read_text(encoding="utf-8"), v), encoding="utf-8", newline="\n")
    return v


if __name__ == "__main__":
    render_docs()
