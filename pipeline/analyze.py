"""Turns data/raw/*.csv into data/out/results.json. Standard library only, no network.

Every number shown on the dashboard, in THESIS.md and in the demo script comes from
results.json. Nothing is typed in by hand.
"""
import csv
import json
import math
import random
import statistics as st
from collections import Counter, defaultdict

from . import config, contiguity, dst_events, sleep

SEED = 20261109
LATEST = "2026-10-01"
PEAK_LOOKBACK = "2024-01-01"
FLAG_MIN_SLEEPERS = 1000     # a family needs this many sleepers before it can be called one program
FLAG_BAND_SHARE = 0.50       # more than this share of its sleepers in 3 neighbouring clock hours marks one program
CRIT_05, CRIT_01 = contiguity.critical_gaps(0.05), contiguity.critical_gaps(0.01)
# Variations on the published rule. Each changes one thing.
VARIANTS = {
    "base": {},
    "alpha_01": {"crit": CRIT_01},
    "hours_8": {"min_hours": 8},
    "hours_10": {"min_hours": 10},
    "gap_max_12": {"hi": 12},
    "gap_max_18": {"hi": 18},
}


def variant_pass(n_days, n_hours, gap, min_hours=6, lo=5, hi=14, crit=CRIT_05, min_days=5):
    return n_days >= min_days and n_hours >= min_hours and lo <= gap <= hi and gap >= crit[n_hours]
TELEGRAM_FAMILIES = {"telegram"}
NAMED_FAMILIES = {"near_name"}
TYPICAL_RECENT = ("2025-03-01", "2026-09-01")   # windows for the "typical" ratio; October 2026 had a one-week burst


def read(name):
    with open(config.RAW / name, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def num(value, default=0.0):
    if value in ("", None):
        return default
    return float(value)


def rate(part, whole):
    return part / whole if whole else 0.0


def band_share(hist):
    total = sum(hist)
    if not total:
        return 0.0
    return max(sum(hist[(i + j) % 24] for j in range(3)) for i in range(24)) / total


# ------------------------------------------------------------------- window table

def build_windows():
    classes = defaultdict(lambda: defaultdict(lambda: {"accounts": 0, "txs": 0}))
    for row in read("classes.csv"):
        slot = classes[row["window_start"]][row["class"]]
        slot["accounts"] += int(row["accounts"])
        slot["txs"] += int(row["txs"])

    families = defaultdict(lambda: defaultdict(lambda: [0] * 24))
    for row in read("families.csv"):
        if row["class"] == "sleeper" and int(row["mid_hour_utc"]) >= 0:
            families[row["window_start"]][row["family"]][int(row["mid_hour_utc"])] += int(row["accounts"])

    market = defaultdict(lambda: {"price": [], "mcap": [], "txns": [], "active": []})
    for row in read("nearblocks_daily.csv"):
        key = row["date"][:7] + "-01"
        if row["date"][8:] <= f"{config.WINDOW_DAYS:02d}":
            market[key]["price"].append(num(row["near_price"]))
            market[key]["mcap"].append(num(row["market_cap"]))
            market[key]["txns"].append(num(row["txns"]))
            market[key]["active"].append(num(row["active_accounts"]))

    intents = defaultdict(float)
    for row in read("defillama_daily.csv"):
        if row["date"][8:] <= f"{config.WINDOW_DAYS:02d}" and row["intents_volume_usd"]:
            intents[row["date"][:7] + "-01"] += num(row["intents_volume_usd"])

    windows, flagged = [], []
    for start in sorted(classes):
        c = classes[start]
        total_accounts = sum(v["accounts"] for v in c.values())
        total_txs = sum(v["txs"] for v in c.values())
        fam = families[start]
        family_counts = {f: sum(h) for f, h in fam.items()}

        excluded = {}
        for f, hist in fam.items():
            share = band_share(hist)
            if family_counts[f] >= FLAG_MIN_SLEEPERS and share >= FLAG_BAND_SHARE:
                excluded[f] = family_counts[f]
                flagged.append({"window": start, "family": f, "sleepers": family_counts[f], "band_share": round(share, 3)})
        sleepers = c["sleeper"]["accounts"]
        humans = sleepers - sum(excluded.values())
        telegram = sum(v for f, v in family_counts.items() if f in TELEGRAM_FAMILIES and f not in excluded)
        named = sum(v for f, v in family_counts.items() if f in NAMED_FAMILIES and f not in excluded)
        other = humans - telegram - named

        hist_h = [0] * 24
        for f, hist in fam.items():
            if f not in excluded:
                for i, v in enumerate(hist):
                    hist_h[i] += v

        regular = sum(c[k]["accounts"] for k in ("sleeper", "routine", "machine", "timer", "unclear"))
        mk = market.get(start, {"price": [], "mcap": [], "txns": [], "active": []})
        windows.append({
            "window": start,
            "accounts": total_accounts,
            "regular_accounts": regular,
            "txs": total_txs,
            "sleepers": sleepers,
            "excluded_programs": sum(excluded.values()),
            "humans": humans,
            "humans_telegram": telegram,
            "humans_named": named,
            "humans_other": other,
            "machines": c["machine"]["accounts"],
            "machine_txs": c["machine"]["txs"],
            "routine": c["routine"]["accounts"],
            "routine_txs": c["routine"]["txs"],
            "timer": c["timer"]["accounts"],
            "unclear": c["unclear"]["accounts"],
            "too_few": c["too_few"]["accounts"],
            "light": c["light"]["accounts"],
            "sleeper_txs": c["sleeper"]["txs"],
            "machine_tx_share": rate(c["machine"]["txs"], total_txs),
            "sleeper_tx_share": rate(c["sleeper"]["txs"], total_txs),
            "price": st.mean(mk["price"]) if mk["price"] else None,
            "mcap": st.mean(mk["mcap"]) if mk["mcap"] else None,
            "nearblocks_tx_sum": sum(mk["txns"]) if mk["txns"] else None,
            "intents_usd": intents.get(start),
            "human_mid_hist": hist_h,
        })
    return windows, flagged


# ------------------------------------------------------------------- outside validation

def verified(windows):
    """Face-verified humans: how many pass, and how that compares with all regular accounts in the same windows."""
    rows = [{k: (row[k] if k in ("class", "window_start") else int(row[k])) for k in row} for row in read("verified.csv")]
    total = sum(r["account_windows"] for r in rows)
    pop = {w["window"]: rate(w["sleepers"], w["regular_accounts"]) for w in windows}

    by_class = Counter()
    gap_hist = [0] * 24
    per_day = []
    expected = 0.0
    for r in rows:
        n = r["account_windows"]
        by_class[r["class"]] += n
        gap_hist[r["gap"]] += n
        per_day += [r["n_slots"] / r["n_days"]] * n
        expected += n * pop.get(r["window_start"], 0.0)
    per_day.sort()
    pass_rate = rate(by_class["sleeper"], total)
    se = math.sqrt(pass_rate * (1 - pass_rate) / total)
    variants = {name: rate(sum(r["account_windows"] for r in rows if variant_pass(r["n_days"], r["n_hours"], r["gap"], **kw)), total)
                for name, kw in VARIANTS.items()}
    baseline = expected / total

    def pass_rate_where(test):
        chosen = [r for r in rows if test(r["window_start"])]
        n = sum(r["account_windows"] for r in chosen)
        return n, rate(sum(r["account_windows"] for r in chosen if r["class"] == "sleeper"), n)

    years = sorted({r["window_start"][:4] for r in rows})
    by_year = {y: dict(zip(("account_windows", "pass_rate"), pass_rate_where(lambda w, y=y: w.startswith(y)))) for y in years}
    last_12 = {w["window"] for w in windows[-12:]}
    recent_n, recent_rate = pass_rate_where(lambda w: w in last_12)
    return {
        "verified_accounts": int(read("verified_meta.csv")[0]["accounts"]),
        "by_year": by_year,
        "recent_account_windows": recent_n,
        "recent_pass_rate": recent_rate,
        "account_windows": total,
        "by_class": dict(by_class),
        "pass_rate": pass_rate,
        "pass_rate_ci_low": pass_rate - 1.96 * se,
        "pass_rate_ci_high": pass_rate + 1.96 * se,
        "same_windows_all_accounts_pass_rate": baseline,
        "lift": pass_rate / baseline if baseline else None,
        "routine_rate": rate(by_class["routine"], total),
        "machine_rate": rate(by_class["machine"], total),
        "gap_hist": gap_hist,
        "median_hours_per_day": per_day[len(per_day) // 2],
        "variants": variants,
    }


def people_estimate(windows, ver, cal):
    """What could the true number of regular people be? Two things are unknown, so this is a grid.

    If real people pass at rate s and everything else passes at rate f, the people share of regular
    accounts is (p - f) / (s - f), where p is the observed pass rate. s is taken from verified humans,
    over all years and over the last 12 windows. f is taken from shuffled accounts and two higher guesses,
    because no labelled set of bots exists to measure it.
    """
    last = {w["window"]: w for w in windows}[LATEST]
    regular = last["regular_accounts"]
    p = rate(last["sleepers"], regular)
    s_options = {"all_years": ver["pass_rate"], "last_12_windows": ver["recent_pass_rate"]}
    f_options = {"shuffled": cal["false_positive_rate"], "five_percent": 0.05, "nine_percent": 0.09}
    grid = {}
    for s_name, s_val in s_options.items():
        grid[s_name] = {}
        for f_name, f_val in f_options.items():
            share = (p - f_val) / (s_val - f_val) if s_val > f_val else 0.0
            grid[s_name][f_name] = max(0.0, min(1.0, share)) * regular
    values = [v for row in grid.values() for v in row.values()]
    return {"pass_share": p, "regular_accounts": regular, "s_options": s_options, "f_options": f_options, "grid": grid,
            "low": min(values), "high": max(values)}


# ------------------------------------------------------------------- headline numbers

def headline(windows, ver, est):
    by = {w["window"]: w for w in windows}
    last = by[LATEST]
    recent = [w for w in windows if w["window"] >= PEAK_LOOKBACK]
    peak = max(recent, key=lambda w: w["humans"])
    named_peak = max(recent, key=lambda w: w["humans_named"])
    typical = [w for w in windows if TYPICAL_RECENT[0] <= w["window"] <= TYPICAL_RECENT[1]]
    typical_ratio = st.median(rate(w["humans"], w["accounts"]) for w in typical)
    typical_ratio_reg = st.median(rate(w["humans"], w["regular_accounts"]) for w in typical)
    prev = by["2026-09-01"]
    return {
        "latest_window": LATEST,
        "latest_label": "1-14 October 2026",
        "accounts": last["accounts"],
        "regular_accounts": last["regular_accounts"],
        "light_accounts": last["light"],
        "light_accounts_prev": prev["light"],
        "txs": last["txs"],
        "sleepers": last["sleepers"],
        "humans": last["humans"],
        "humans_telegram": last["humans_telegram"],
        "humans_named": last["humans_named"],
        "humans_other": last["humans_other"],
        "routine": last["routine"],
        "telegram_share": rate(last["humans_telegram"], last["humans"]),
        "machines": last["machines"],
        "machine_tx_share": last["machine_tx_share"],
        "sleeper_tx_share": last["sleeper_tx_share"],
        "people_per_100_regular": rate(last["humans"], last["regular_accounts"]) * 100,
        "people_per_100_accounts": rate(last["humans"], last["accounts"]) * 100,
        "typical_people_per_100": typical_ratio * 100,
        "typical_people_per_100_regular": typical_ratio_reg * 100,
        "estimated_people_low": est["low"],
        "estimated_people_high": est["high"],
        "peak_window": peak["window"],
        "peak_humans": peak["humans"],
        "decline_from_peak": 1 - rate(last["humans"], peak["humans"]),
        "named_peak_window": named_peak["window"],
        "named_peak": named_peak["humans_named"],
        "named_decline": 1 - rate(last["humans_named"], named_peak["humans_named"]),
        "decline_adjusted": 1 - rate(last["humans"] / ver["by_year"][LATEST[:4]]["pass_rate"], peak["humans"] / ver["by_year"][peak["window"][:4]]["pass_rate"]),
        "price": last["price"],
        "mcap": last["mcap"],
    }


# ------------------------------------------------------------------- cross-checks

def crosscheck(windows):
    """Does the BigQuery pipeline agree with an independent public source?"""
    ratios = []
    for w in windows:
        if w["nearblocks_tx_sum"]:
            ratios.append({"window": w["window"], "bigquery": w["txs"], "nearblocks": w["nearblocks_tx_sum"],
                           "ratio": w["txs"] / w["nearblocks_tx_sum"]})
    within = sum(1 for r in ratios if abs(r["ratio"] - 1) <= 0.01)
    nb = {r["date"]: r for r in read("nearblocks_daily.csv")}
    daily = []
    for row in read("daily_totals.csv"):
        other = nb.get(row["block_date"])
        if other:
            daily.append({
                "date": row["block_date"],
                "tx_ratio": int(row["transactions"]) / num(other["txns"]),
                "acct_ratio": int(row["active_accounts"]) / num(other["active_accounts"]),
                "bq_tx": int(row["transactions"]),
                "bq_accounts": int(row["active_accounts"]),
                "bq_contracts": int(row["contracts_called"]),
            })
    return {
        "windows_compared": len(ratios),
        "windows_within_1pct": within,
        "worst_ratio": max(ratios, key=lambda r: abs(r["ratio"] - 1)),
        "daily_days": len(daily),
        "daily_tx_within_1pct": sum(1 for d in daily if abs(d["tx_ratio"] - 1) <= 0.01),
        "daily_acct_within_1pct": sum(1 for d in daily if abs(d["acct_ratio"] - 1) <= 0.01),
        "daily": daily,
    }


# ------------------------------------------------------------------- chance calibration

def calibration():
    rng = random.Random(SEED)
    real_counts, null_counts = Counter(), Counter()
    real_gaps, null_gaps = Counter(), Counter()
    false_counts = Counter()
    rows = read("calibration_masks.csv")
    for row in rows:
        days = [int(x, 16) for x in row["day_masks"].split(",")]
        real = sleep.classify(days)
        real_counts[real["class"]] += 1
        real_gaps[real["gap"]] += 1
        rotated = [sleep.rotate(m, rng.randrange(24)) for m in days]
        null = sleep.classify(rotated)
        null_counts[null["class"]] += 1
        null_gaps[null["gap"]] += 1
        for name, kw in VARIANTS.items():
            false_counts[name] += variant_pass(null["n_days"], null["n_hours"], null["gap"], **kw)
    n = len(rows)
    return {
        "accounts": n,
        "real": dict(real_counts),
        "null": dict(null_counts),
        "false_positive_rate": rate(null_counts["sleeper"], n),
        "real_sleeper_rate": rate(real_counts["sleeper"], n),
        "variant_false_rates": {name: rate(false_counts[name], n) for name in VARIANTS},
        "expected_false_share_of_sleepers": rate(null_counts["sleeper"], real_counts["sleeper"]),
        "gap_real": [real_gaps[g] for g in range(24)],
        "gap_null": [null_gaps[g] for g in range(24)],
    }


# ------------------------------------------------------------------- clocks

def clock_profiles():
    table = defaultdict(lambda: defaultdict(lambda: [0] * 24))
    for row in read("clock.csv"):
        table[row["window_start"]][row["class"]][int(row["hour"])] = int(row["accounts"])
    return {key: {c: table[key][c] for c in ("sleeper", "machine", "timer", "unclear")} for key in (LATEST, "2025-01-01")}


# ------------------------------------------------------------------- daylight-saving experiment

def _interp(hist, x):
    x %= 24
    i = int(x)
    f = x - i
    return hist[i] * (1 - f) + hist[(i + 1) % 24] * f


def best_shift(pre, post):
    """Shift (hours) that best lines up the 'pre' clock with the 'post' clock."""
    pre_share = [v / sum(pre) for v in pre]
    post_share = [v / sum(post) for v in post]
    best = None
    for k in range(-30, 31):
        d = k / 10
        moved = [_interp(pre_share, i - d) for i in range(24)]
        m1, m2 = sum(moved) / 24, sum(post_share) / 24
        cov = sum((a - m1) * (b - m2) for a, b in zip(moved, post_share))
        v1 = sum((a - m1) ** 2 for a in moved)
        v2 = sum((b - m2) ** 2 for b in post_share)
        corr = cov / math.sqrt(v1 * v2) if v1 and v2 else 0.0
        if best is None or corr > best[0]:
            best = (corr, d)
    return best[1]


def dst():
    hist = defaultdict(lambda: [0] * 24)
    for row in read("dst.csv"):
        hist[(row["event"], row["grp"], row["period"])][int(row["hour"])] += int(row["slots"])

    rows = []
    for name, day, direction, region in dst_events.EVENTS:
        groups = {}
        for grp in ("europe", "americas", "asia", "machines"):
            a, b = hist[(name, grp, "pre")], hist[(name, grp, "post")]
            if sum(a) >= 300 and sum(b) >= 300:
                groups[grp] = best_shift(a, b)
        rows.append({"event": name, "date": day, "direction": direction, "region": region, "shifts": groups})

    real = [r for r in rows if r["direction"] != 0]
    placebo = [r for r in rows if r["direction"] == 0]
    effects = [(r["shifts"][r["region"]] - r["shifts"]["asia"]) * r["direction"]
               for r in real if r["region"] in r["shifts"] and "asia" in r["shifts"]]
    noise = [r["shifts"][grp] - r["shifts"]["asia"] for r in placebo for grp in ("europe", "americas")
             if grp in r["shifts"] and "asia" in r["shifts"]]
    sd = st.pstdev(noise) if len(noise) > 1 else 0.0
    mean = st.mean(effects) if effects else 0.0
    se = sd / math.sqrt(len(effects)) if effects else 0.0
    return {
        "rows": rows,
        "mean_signed_effect": mean,
        "effects": effects,
        "placebo_sd": sd,
        "placebo_noise": noise,
        "n_events": len(effects),
        "ci_low": mean - 1.96 * se,
        "ci_high": mean + 1.96 * se,
    }


# ------------------------------------------------------------------- retention

def retention(flagged):
    excluded_windows = {f["window"] for f in flagged}
    pooled = defaultdict(lambda: [0, 0])
    recent = defaultdict(lambda: [0, 0])
    months = sorted({int(r["months_later"]) for r in read("retention.csv")})
    for row in read("retention.csv"):
        key = (row["class"], int(row["months_later"]))
        if row["window_start"] in excluded_windows:
            continue
        pooled[key][0] += int(row["cohort"])
        pooled[key][1] += int(row["seen_again"])
        if row["window_start"] >= "2025-01-01":
            recent[key][0] += int(row["cohort"])
            recent[key][1] += int(row["seen_again"])
    twelve = defaultdict(dict)
    for row in read("retention.csv"):
        if int(row["months_later"]) == 12 and row["class"] in ("sleeper", "machine") and row["window_start"] not in excluded_windows:
            twelve[row["window_start"]][row["class"]] = rate(int(row["seen_again"]), int(row["cohort"]))
    last_three = sorted(twelve)[-3:]
    out = {"all_windows": {}, "since_2025": {}, "last_three_12m_cohorts": [
        {"window": w, "sleeper": twelve[w].get("sleeper"), "machine": twelve[w].get("machine")} for w in last_three]}
    for cls in ("sleeper", "routine", "machine", "timer", "unclear", "too_few"):
        out["all_windows"][cls] = {m: rate(pooled[(cls, m)][1], pooled[(cls, m)][0]) for m in months}
        out["since_2025"][cls] = {m: rate(recent[(cls, m)][1], recent[(cls, m)][0]) for m in months}
    return out


# ------------------------------------------------------------------- trend

def trend(windows):
    """Simple straight-line fit of log(people) over the last 12 windows."""
    recent = windows[-12:]
    ys = [math.log(w["humans"]) for w in recent]
    xs = list(range(len(ys)))
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    monthly = math.exp(slope) - 1
    latest = windows[-1]["humans"]
    peak = max(w["humans"] for w in windows if w["window"] >= PEAK_LOOKBACK)
    return {
        "months_used": len(recent),
        "monthly_change": monthly,
        "half_life_months": math.log(2) / abs(slope) if slope < 0 else None,
        "latest": latest,
        "peak": peak,
        "projected_12m": latest * (1 + monthly) ** 12,
        "projected_24m": latest * (1 + monthly) ** 24,
        "growth_needed_to_regain_peak_in_5y": (peak / latest) ** (1 / 60) - 1,
    }


# ------------------------------------------------------------------- lead/lag

def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    return cov / math.sqrt(vx * vy) if vx and vy else float("nan")


def perm_p(xs, ys, draws=5000, seed=SEED):
    observed = abs(pearson(xs, ys))
    rng = random.Random(seed)
    shuffled = list(ys)
    extreme = 0
    for _ in range(draws):
        rng.shuffle(shuffled)
        if abs(pearson(xs, shuffled)) >= observed:
            extreme += 1
    return (extreme + 1) / (draws + 1)


def lead_lag(windows):
    series = {"humans": "humans", "headline_accounts": "accounts", "txs": "txs", "price": "price", "intents_volume": "intents_usd"}
    usable = [w for w in windows if w["window"] >= "2022-01-01"]

    def deltas(key):
        out = {}
        for prev, cur in zip(usable[:-1], usable[1:]):
            a, b = prev.get(key), cur.get(key)
            if a and b and a > 0 and b > 0:
                out[cur["window"]] = math.log(b / a)
        return out

    delta = {name: deltas(col) for name, col in series.items()}
    tests = []
    order = [w["window"] for w in usable]
    index = {w: i for i, w in enumerate(order)}
    for signal in ("humans", "headline_accounts", "txs", "intents_volume"):
        for lag in (-3, -2, -1, 0, 1, 2, 3):      # lag > 0: signal earlier than price
            xs, ys = [], []
            for window, value in delta[signal].items():
                i = index[window] + lag
                if 0 <= i < len(order) and order[i] in delta["price"]:
                    xs.append(value)
                    ys.append(delta["price"][order[i]])
            if len(xs) >= 10:
                tests.append({"signal": signal, "lag_months": lag, "n": len(xs), "r": pearson(xs, ys), "p": perm_p(xs, ys)})

    def best_positive(sig):
        rows = [t for t in tests if t["signal"] == sig and t["lag_months"] > 0]
        return min(rows, key=lambda t: t["p"]) if rows else None

    pairs = [(delta["humans"][w], delta["headline_accounts"][w]) for w in delta["humans"] if w in delta["headline_accounts"]]
    significant = [t for t in tests if t["p"] < 0.05]
    k, n = len(significant), len(tests)
    chance = sum(math.comb(n, i) * 0.05 ** i * 0.95 ** (n - i) for i in range(k, n + 1))
    return {
        "significant_tests": significant,
        "chance_of_this_many": chance,
        "significant_count": len(significant),
        "tests": tests,
        "best_lead_humans": best_positive("humans"),
        "best_lead_headline": best_positive("headline_accounts"),
        "best_lead_txs": best_positive("txs"),
        "best_lead_intents": best_positive("intents_volume"),
        "humans_vs_headline_r": pearson([a for a, _ in pairs], [b for _, b in pairs]),
        "n_tests": len(tests),
    }


# ------------------------------------------------------------------- relayed humans

def relayed():
    out = {}
    for row in read("relayed.csv"):
        w = row["window_start"]
        slot = out.setdefault(w, {"relayed_sleepers_total": 0, "relayed_only_sleepers": 0, "relayed_sleepers_not_counted_as_signers": 0,
                                  "relayed_accounts_total": 0, "delegate_actions": 0, "delegate_actions_non_machine": 0})
        n, actions = int(row["accounts"]), int(row["delegate_actions"])
        slot["relayed_accounts_total"] += n
        slot["delegate_actions"] += actions
        if row["relayed_class"] != "machine":
            slot["delegate_actions_non_machine"] += actions
        if row["relayed_class"] == "sleeper":
            slot["relayed_sleepers_total"] += n
            if row["signer_class"] == "no_signed_txs":
                slot["relayed_only_sleepers"] += n
            if row["signer_class"] != "sleeper":
                slot["relayed_sleepers_not_counted_as_signers"] += n
    return out


# ------------------------------------------------------------------- what people use

def apps():
    by_window = defaultdict(list)
    for row in read("apps.csv"):
        by_window[row["window_start"]].append({k: (int(v) if k not in ("window_start", "contract") else v) for k, v in row.items()})
    latest = sorted(by_window[LATEST], key=lambda r: -r["sleepers"])
    busiest = sorted(by_window[LATEST], key=lambda r: -r["txs"])
    keys = ("contract", "sleepers", "signers", "txs", "machine_txs")
    game = next((r for r in by_window[LATEST] if r["contract"] == "game.hot.tg"), None)
    return {
        "game_sleepers": game["sleepers"] if game else 0,
        "latest_top_by_sleepers": [{k: r[k] for k in keys} for r in latest[:12]],
        "latest_top_by_txs": [{k: r[k] for k in keys} for r in busiest[:12]],
    }


def concentration(windows):
    """Shares use every transaction in the window, including accounts seen on only one or two days."""
    txs = {w["window"]: w["txs"] for w in windows}
    rows = []
    for row in read("concentration.csv"):
        total = txs[row["window_start"]]
        rows.append({"window": row["window_start"], "top_10": rate(float(row["top_10"]), total), "top_100": rate(float(row["top_100"]), total),
                     "top100_machines": int(row["top100_machines"]), "top100_sleepers": int(row["top100_sleepers"])})
    return rows


def sensitivity():
    row = [r for r in read("sensitivity.csv") if r["window_start"] == LATEST][0]
    base = int(row["base"])
    return {k: {"count": int(v), "versus_base": rate(int(v), base) - 1} for k, v in row.items() if k != "window_start"}


def timezones(windows):
    by = {w["window"]: w["human_mid_hist"] for w in windows}
    out = {}
    for key in (LATEST, "2025-01-01"):
        hist = by[key]
        offs = Counter()
        for hour, count in enumerate(hist):
            offs[(int(round(config.TYPICAL_SLEEP_MIDPOINT_LOCAL - (hour + 0.5))) + 12) % 24 - 12] += count
        out[key] = {"offset_counts": [offs[o] for o in range(-12, 12)], "total": sum(hist)}
    return out


def intents_context(windows):
    rows = [w for w in windows if w["window"] >= "2025-01-01" and w["intents_usd"]]
    first, last = rows[0], rows[-1]
    low = min((w for w in windows if w["window"] >= "2025-01-01" and w["price"]), key=lambda w: w["price"])
    return {"price_low": low["price"], "price_low_window": low["window"], "first_window": first["window"],
            "first_14d_usd": first["intents_usd"], "latest_14d_usd": last["intents_usd"]}


def rounded(value):
    """Floats are written to 6 decimals, so the file is byte-identical across operating systems."""
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, dict):
        return {k: rounded(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [rounded(v) for v in value]
    return value


def main():
    config.OUT.mkdir(parents=True, exist_ok=True)
    windows, flagged = build_windows()
    ver = verified(windows)
    cal = calibration()
    est = people_estimate(windows, ver, cal)
    results = {
        "headline": headline(windows, ver, est),
        "people_estimate": est,
        "windows": windows,
        "flagged_programs": flagged,
        "crosscheck": crosscheck(windows),
        "calibration": cal,
        "verified": ver,
        "clock": clock_profiles(),
        "dst": dst(),
        "retention": retention(flagged),
        "trend": trend(windows),
        "lead_lag": lead_lag(windows),
        "relayed": relayed(),
        "apps": apps(),
        "concentration": concentration(windows),
        "sensitivity": sensitivity(),
        "timezones": timezones(windows),
        "intents": intents_context(windows),
        "config": {
            "min_days": config.MIN_DAYS, "min_hours": config.MIN_HOURS, "min_gap": config.MIN_GAP, "max_gap": config.MAX_GAP,
            "machine_max_gap": config.MACHINE_MAX_GAP, "machine_min_hours_per_day": config.MACHINE_MIN_HOURS_PER_DAY,
            "timer_max_hours": config.TIMER_MAX_HOURS, "alpha": config.ALPHA, "window_days": config.WINDOW_DAYS,
        },
    }
    results = rounded(results)
    path = config.OUT / "results.json"
    path.write_bytes((json.dumps(results, indent=1, default=str) + "\n").encode("utf-8"))
    return results


if __name__ == "__main__":
    main()
