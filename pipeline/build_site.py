"""Builds site/index.html (the static dashboard) and site/test.html from data/out/results.json."""
import csv
import json
import statistics as st

from . import charts as C
from . import config, contiguity, sleep
from .charts import esc, full, pct

ACCENT = {
    "people": "var(--s-people)",
    "machines": "var(--s-machines)",
    "timers": "var(--s-timers)",
    "unclear": "var(--s-unclear)",
    "telegram": "var(--s-people)",
    "named": "var(--s-timers)",
    "other": "var(--s-unclear)",
    "price": "var(--s-timers)",
    "intents": "var(--s-machines)",
}


# ---- the SQL shown under each chart ---------------------------------------------------

def show_sql(name, **extra) -> str:
    """The query as shown on the page. Long literal lists are abbreviated, and the page says so."""
    from .pull_bigquery import class_case, crit_array
    text = (config.SQL / name).read_text(encoding="utf-8")
    defaults = dict(
        project="your-project", dataset=config.DATASET, source=config.SOURCE,
        min_days=config.MIN_DAYS,
        class_case=class_case(), class_case_inline=class_case(gap="g.gap", hours="ARRAY_LENGTH(hs)"),
        crit_05=crit_array(0.05), crit_01=crit_array(0.01),
        window_filter="block_date BETWEEN ... -- 70 two-week windows, listed in pipeline/config.py",
        app_filter="block_date BETWEEN ... -- sample windows, see pipeline/config.py",
        dst_filter="block_date BETWEEN ... -- days around each clock change, see pipeline/dst_events.py",
        dst_sql="[ ... the clock-change dates, see pipeline/dst_events.py ... ]",
        relayed_filter="block_date BETWEEN ... -- see pipeline/config.py",
        relayed_windows=", ".join(config.RELAYED_WINDOWS),
        verified_list="[ ... the verified account names, read from the chain by pipeline/pull_verified.py ... ]",
        verified_count="the verified",
    )
    defaults.update(extra)
    return text.format(**defaults).strip()


def details(sql_files, table_html=None) -> str:
    out = []
    if sql_files:
        out.append('<details class="d"><summary>The query behind this chart</summary>')
        out.append('<p class="file">Long lists are shortened here. <code class="i">python -m pipeline.pull_bigquery --print 10</code> prints any step in full, ready to paste. Steps other than 10 and 15 read the table built by step 00.</p>')
        for name in sql_files:
            out.append(f'<p class="file">sql/{esc(name)}</p><pre><code>{esc(show_sql(name))}</code></pre>')
        out.append("</details>")
    if table_html:
        out.append(f'<details class="d"><summary>The numbers as a table</summary>{table_html}</details>')
    return "".join(out)


def panel(pid, question, says, body, sql_files=None, table_html=None) -> str:
    return (f'<article class="panel" id="{pid}"><h3>{esc(question)}</h3><p class="says">{says}</p>'
            f'<div class="plot">{body}</div>{details(sql_files, table_html)}</article>')


# ---- hero examples --------------------------------------------------------------------

def pick_examples():
    """Three real accounts from the chance-check sample (no names, drawn from the masks)."""
    rows = []
    with open(config.RAW / "calibration_masks.csv", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            days = [int(x, 16) for x in row["day_masks"].split(",")]
            rows.append((days, sleep.classify(days)))

    def pick(condition, key):
        return max((r for r in rows if condition(r[1])), key=key)

    person = pick(lambda c: c["class"] == "sleeper" and c["n_days"] >= 11 and 7 <= c["gap"] <= 10 and c["n_hours"] >= 12,
                  key=lambda r: (r[1]["n_days"], r[1]["n_slots"]))
    machine = pick(lambda c: c["class"] == "machine" and c["n_days"] == 14 and c["gap"] == 0,
                   key=lambda r: (r[1]["n_slots"] < 330, r[1]["n_slots"]))
    timer = pick(lambda c: c["class"] == "timer" and c["n_days"] >= 12 and c["n_hours"] <= 2,
                 key=lambda r: r[1]["n_days"])
    return person, machine, timer


def actogram(days, info, band=False) -> str:
    rows, row_h, cell = 14, 11, 11
    left, top = 12, 20
    width = left + 24 * cell + 12
    height = top + rows * row_h + 8
    out = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Activity by hour for each active day">']
    if band:
        start = (info["mid"] - info["gap"] / 2) % 24
        for i in range(info["gap"]):
            col = int((start + i) % 24)
            out.append(f'<rect x="{left + col * cell}" y="{top}" width="{cell}" height="{rows * row_h}" class="sleep-band"/>')
    for d, mask in enumerate(days[:rows]):
        for h in range(24):
            if (mask >> h) & 1:
                out.append(f'<rect x="{left + h * cell + 1}" y="{top + d * row_h + 1}" width="{cell - 2}" height="{row_h - 2}" rx="1.5" class="tick"/>')
    for h in (0, 6, 12, 18, 24):
        out.append(f'<line x1="{left + h * cell}" x2="{left + h * cell}" y1="{top - 3}" y2="{top + rows * row_h}" class="rule-night"/>')
        out.append(f'<text x="{left + h * cell}" y="{top - 7}" text-anchor="middle" class="axis-night">{h % 24:02d}</text>')
    out.append("</svg>")
    return "".join(out)


def examples_html() -> str:
    (p_days, p_info), (m_days, m_info), (t_days, t_info) = pick_examples()
    return f"""
    <div class="examples" id="examples">
      <figure class="ex">
        {actogram(p_days, p_info, band=True)}
        <figcaption><strong>Sleeps.</strong> Never active during the same {p_info["gap"]} hours, and active at many other hours across two weeks.</figcaption>
      </figure>
      <figure class="ex">
        {actogram(m_days, m_info)}
        <figcaption><strong>Never sleeps.</strong> Active in nearly every hour of every day. A program.</figcaption>
      </figure>
      <figure class="ex">
        {actogram(t_days, t_info)}
        <figcaption><strong>On a timer.</strong> Always the same hour of the day and never anything else.</figcaption>
      </figure>
    </div>"""


# ---- findings -------------------------------------------------------------------------

def tiles(R) -> str:
    h = R["headline"]
    items = [
        (full(h["humans"]), "accounts passed the sleep test",
         f"Out of {full(h['regular_accounts'])} accounts active on at least 5 of those 14 days. This is not a head count: the test misses most verified humans, and some accounts pass by chance."),
        (pct(h["machine_tx_share"], 0), f"of transactions came from {full(h['machines'])} accounts that never sleep",
         f"The other {full(h['regular_accounts'] - h['machines'])} regular accounts and the {full(h['light_accounts'] + (h['accounts'] - h['regular_accounts'] - h['light_accounts']))} occasional ones share the rest."),
        (f"−{h['decline_from_peak'] * 100:.0f}%", "accounts passing since " + C.month_label(h["peak_window"]),
         f"{full(h['peak_humans'])} then. {full(h['humans'])} now."),
        (pct(h["telegram_share"], 0), "of accounts passing are Telegram accounts",
         f"Named .near accounts that pass: {full(h['humans_named'])}, up from a {C.month_label('2026-07-01')} low of {full(next(w['humans_named'] for w in R['windows'] if w['window'] == '2026-07-01'))}, but far below {full(h['named_peak'])} in {C.month_label(h['named_peak_window'])}."),
    ]
    cells = "".join(f'<div class="tile"><div class="tile-value">{esc(v)}</div><div class="tile-label">{esc(t)}</div><p>{esc(s)}</p></div>' for v, t, s in items)
    return f'<div class="tiles">{cells}</div>'


def fig_accounts(R):
    W = R["windows"]
    h = R["headline"]
    body = C.line_log(W, [("accounts", "Active accounts", ACCENT["machines"]),
                          ("regular_accounts", "Active on 5+ of 14 days", ACCENT["unclear"]),
                          ("humans", "Passed the sleep test", ACCENT["people"])],
                      "Active accounts, regular accounts and accounts that pass the sleep test, per two-week window, log scale", start=0)
    says = (f"In the latest window {full(h['accounts'])} accounts were active, but {full(h['light_accounts'])} of them showed up on only one or two days, "
            f"up from {full(h['light_accounts_prev'])} the month before. The count of active accounts swings on bursts like that. "
            f"The accounts that pass the test barely move with it: monthly changes correlate at {R['lead_lag']['humans_vs_headline_r']:.2f}.")
    rows = [[w["window"], full(w["accounts"]), full(w["regular_accounts"]), full(w["humans"]), full(w["routine"]), full(w["machines"]), full(w["txs"])] for w in W]
    return panel("accounts", "Active accounts or actual people?", says, body,
                 ["00_account_windows.sql", "01_classes.sql"],
                 C.table(["Window (first 14 days of)", "Active accounts", "Active on 5+ of 14 days", "Passed sleep test", "Narrow daily routine", "Never sleeps", "Transactions"], rows))


def fig_machines(R):
    W = R["windows"]
    last = R["concentration"][-1]
    rel = R["relayed"]["2026-10-01"]
    latest = W[-1]
    body = C.line_share(W, "machine_tx_share", "Share of transactions from accounts that never sleep", ACCENT["machines"],
                        "Share of all transactions sent by always-on accounts, per window")
    says = (f"Accounts that never sleep sent {pct(latest['machine_tx_share'], 0)} of all transactions in the latest window. "
            f"Of the 100 busiest accounts, {last['top100_machines']} are machines and {last['top100_sleepers']} sleep, and those 100 sent {pct(last['top_100'], 0)} of everything. "
            f"Some of this traffic is relayers acting for other accounts: such delegated actions from accounts that do not themselves look like machines were {pct(rel['delegate_actions_non_machine'] / latest['txs'], 0)} of all transactions.")
    rows = [[w["window"], pct(w["machine_tx_share"]), pct(w["sleeper_tx_share"])] for w in W]
    return panel("machines", "Who actually sends the transactions?", says, body,
                 ["01_classes.sql", "07_concentration.sql"], C.table(["Window", "Never-sleeping accounts' share of transactions", "Sleepers' share"], rows))


def fig_families(R):
    W = R["windows"]
    h = R["headline"]
    flagged = R["flagged_programs"]
    body = C.stacked_columns(W, [("humans_named", "Named .near accounts", ACCENT["named"]),
                                 ("humans_other", "Other accounts", ACCENT["other"]),
                                 ("humans_telegram", "Telegram accounts", ACCENT["telegram"])],
                             "Accounts passing the sleep test, by kind of account, per window", start=0)
    says = (f"{pct(h['telegram_share'], 0)} of the accounts that pass today are Telegram accounts, and {pct(R['apps']['game_sleepers'] / h['sleepers'], 0)} use one game. "
            f"Named .near accounts peaked at {full(h['named_peak'])} in {C.month_label(h['named_peak_window'])}. "
            f"{len(flagged)} windows contained large groups of accounts all sleeping in the same few hours, which looks like one program. Those groups are excluded here and listed below.")
    rows = [[f["window"], f["family"], full(f["sleepers"]), pct(f["band_share"], 0)] for f in flagged]
    return panel("families", "Who passes the test?", says, body,
                 ["11_families.sql"], C.table(["Window", "Account family", "Sleepers removed", "Share in 3 neighbouring hours"], rows))


def fig_apps(R):
    latest = R["apps"]["latest_top_by_sleepers"]
    rows_txt = [[r["contract"], full(r["sleepers"]), full(r["signers"]), full(r["txs"]), pct(r["machine_txs"] / r["txs"] if r["txs"] else 0, 0)] for r in latest]
    body = C.grouped_bars_h([(r["contract"], r["sleepers"]) for r in latest[:8]], "Sleepers per contract", ACCENT["people"])
    txs = R["apps"]["latest_top_by_txs"]
    intents = next((r for r in txs if r["contract"] == "intents.near"), None)
    extra = ""
    if intents:
        extra = (f" By contrast, {pct(intents['machine_txs'] / intents['txs'], 0)} of the {full(intents['txs'])} transactions sent to intents.near "
                 f"were signed by machines. People using cross-chain swaps usually sign off-chain, so they never appear here.")
    says = "The contracts sleepers use most are the HOT game and its airdrops, then wrapped NEAR, then a long thin tail." + extra
    return panel("apps", "What do these accounts use?", says, body, ["09_apps.sql"],
                 C.table(["Contract", "Sleepers", "All signers", "Transactions", "Sent by machines"], rows_txt))


def fig_retention(R):
    ret = R["retention"]["since_2025"]
    names = {"sleeper": "Sleepers", "routine": "Narrow daily routine", "machine": "Never sleeps", "timer": "On a timer", "unclear": "Can't tell"}
    rows = [[names[c], pct(ret[c]["1"], 0), pct(ret[c]["3"], 0), pct(ret[c]["6"], 0), pct(ret[c]["12"], 0)] for c in names]
    recent = R["retention"]["last_three_12m_cohorts"]
    says = (f"Of accounts that passed the test in a window since January 2025, {pct(ret['sleeper']['12'], 0)} were still regularly active a year later, "
            f"compared with {pct(ret['machine']['12'], 0)} of accounts that never sleep. The most recent cohorts go the other way: "
            f"in the three latest that can be measured, sleepers held {pct(st.mean(c['sleeper'] for c in recent), 0)} and machines {pct(st.mean(c['machine'] for c in recent), 0)}. "
            "Windows flagged as a single program are left out.")
    return panel("retention", "Do they stay?", says, C.table(["Kind of account", "1 month later", "3 months", "6 months", "12 months"], rows),
                 ["05_retention.sql"])


def fig_relayed(R):
    rel = R["relayed"]
    W = {w["window"]: w for w in R["windows"]}
    rows = []
    for key in sorted(rel):
        rows.append({"window": key, "signers": W[key]["sleepers"], "relayed": rel[key]["relayed_sleepers_not_counted_as_signers"]})
    latest, first_rel = rows[-1], rows[0]
    body = C.stacked_columns(rows, [("signers", "Sleep test passed as a signer", ACCENT["people"]),
                                    ("relayed", "Sleep test passed only through a gas relayer", ACCENT["other"])],
                             "Accounts passing the test as signers and through relayers", height=270, start=0, label_each=True)
    says = (f"Some people never sign anything: a relayer pays the gas and signs for them. Running the same test on those accounts adds "
            f"{full(latest['relayed'])} in the latest window, so the count of accounts that pass is closer to {full(latest['signers'] + latest['relayed'])}. "
            f"That group is shrinking too: it was {full(first_rel['relayed'])} in April 2026.")
    tab = [[r["window"], full(r["signers"]), full(r["relayed"]), full(rel[r["window"]]["relayed_accounts_total"])] for r in rows]
    return panel("relayed", "Are people hidden behind relayers?", says, body, ["12_relayed.sql"],
                 C.table(["Window", "Passed as signers", "Passed, relayed only", "All relayed accounts"], tab))


def fig_divergence(R):
    W = [w for w in R["windows"] if w["window"] >= "2025-01-01"]
    body = C.indexed_lines(W, [("humans", "Accounts passing the sleep test", ACCENT["people"], full),
                               ("price", "NEAR price", ACCENT["price"], lambda v: f"${v:.2f}"),
                               ("intents_usd", "NEAR Intents swap volume", ACCENT["intents"], lambda v: "$" + C.compact(v))],
                           "Accounts passing the test, price and Intents volume, indexed to 100 in January 2025, log scale")
    first, last = W[0], W[-1]
    says = (f"Since January 2025 the number of accounts passing the test fell {(1 - last['humans'] / first['humans']) * 100:.0f}%. "
            f"Over the same stretch two-week swap volume through NEAR Intents grew from ${C.compact(first['intents_usd'])} to ${C.compact(last['intents_usd'])}, "
            f"and the price went from ${first['price']:.2f} to ${last['price']:.2f} after a low of ${R['intents']['price_low']:.2f}. "
            f"More money flows through NEAR while fewer accounts that look like people use it.")
    rows = [[w["window"], full(w["humans"]), f"${w['price']:.2f}", f"${C.compact(w['intents_usd'])}" if w["intents_usd"] else "n/a"] for w in W]
    return panel("divergence", "Did value follow the people?", says, body, ["01_classes.sql"],
                 C.table(["Window", "Passed sleep test", "Average price", "Intents volume in window"], rows))


def fig_leadlag(R):
    ll = R["lead_lag"]
    signals = [("humans", "Passed the sleep test"), ("headline_accounts", "Active accounts"), ("txs", "Transactions"), ("intents_volume", "Intents volume")]
    lags = [-3, -2, -1, 0, 1, 2, 3]
    by = {(t["signal"], t["lag_months"]): t for t in ll["tests"]}
    rows = []
    for key, name in signals:
        row = [name]
        for lag in lags:
            t = by.get((key, lag))
            row.append(f"{t['r']:+.2f}" + ("*" if t["p"] < 0.05 else "") if t else "")
        rows.append(row)
    best = ll["best_lead_humans"]
    says = (f"Monthly changes in the number of accounts passing the test do not lead the price by 1, 2 or 3 months (best correlation {best['r']:+.2f}, p = {best['p']:.2f}). "
            f"{ll['significant_count']} of the {ll['n_tests']} tests in this table cross p &lt; 0.05 where about {ll['n_tests'] * 0.05:.1f} are expected by chance, a borderline excess. "
            f"The strongest result runs the other way: price moves first and active accounts follow one month later.")
    return panel("leadlag", "Does anything lead the price?", says,
                 C.table(["Signal vs price", "price leads by 3 months", "2", "1", "same month", "signal leads by 1", "2", "3"], rows), ["01_classes.sql"])


def fig_verified(R):
    v, cal = R["verified"], R["calibration"]
    est = R["people_estimate"]
    bars = [("Accounts verified as humans by a face scan", v["pass_rate"]),
            ("All regular accounts, same windows", v["same_windows_all_accounts_pass_rate"]),
            ("Accounts with each day shuffled around the clock", cal["false_positive_rate"])]
    body = C.grouped_bars_h(bars, "Pass rates", ACCENT["people"], value_fmt=lambda x: pct(x, 1), max_value=max(b for _, b in bars))
    by = v["by_year"]
    says = (f"NEAR's I-Am-Human registry holds {full(v['verified_accounts'])} accounts verified as unique humans by a face scan. Of the windows where they were regularly active, "
            f"{pct(v['pass_rate'], 0)} pass, against {pct(cal['false_positive_rate'], 1)} of accounts with their days shuffled. "
            f"So the test does find people, but it misses most of them, and it misses more over time: "
            f"{pct(by['2023']['pass_rate'], 0)} of verified windows passed in 2023 and {pct(by['2026']['pass_rate'], 0)} in 2026.")
    rows = [[k, full(cal["real"].get(k, 0)), full(v["by_class"].get(k, 0))] for k in ("sleeper", "routine", "machine", "timer", "unclear")]
    rows += [[f"Verified windows passing, {y}", "", f"{pct(by[y]['pass_rate'], 0)} of {full(by[y]['account_windows'])}"] for y in sorted(by)]
    return panel("verified", "Does the test find real people?", says, body, ["16_verified.sql"],
                 C.table(["Class", "Sample of all accounts (days not shuffled)", "Verified humans (account-windows)"], rows))


def fig_range(R):
    est = R["people_estimate"]
    h = R["headline"]
    names_s = {"all_years": f"Real people pass {pct(est['s_options']['all_years'], 0)} of the time (all years)",
               "last_12_windows": f"Real people pass {pct(est['s_options']['last_12_windows'], 0)} of the time (last 12 windows)"}
    heads = ["", f"Non-people pass {pct(est['f_options']['shuffled'], 0)} (shuffled accounts)", "Non-people pass 5%", "Non-people pass 9%"]
    rows = [[names_s[k]] + [full(round(est["grid"][k][f], -2)) for f in ("shuffled", "five_percent", "nine_percent")] for k in ("all_years", "last_12_windows")]
    says = (f"The count of accounts passing is {full(h['humans'])}. How many regular people that implies depends on two rates nobody can measure precisely: how often real people pass, "
            f"and how often everything else does. Across plausible values the answer runs from about {full(round(est['low'], -2))} to about {full(round(est['high'], -2))}, out of {full(est['regular_accounts'])} regular accounts. "
            f"So this project does not publish a single figure for it.")
    return panel("range", "So how many people is that?", says, C.table(heads, rows), ["16_verified.sql"])


def fig_gaps(R):
    cal, v = R["calibration"], R["verified"]
    def share(values):
        total = sum(values)
        return [x / total for x in values]
    real, null, ver = share(cal["gap_real"]), share(cal["gap_null"]), share(v["gap_hist"])
    body = C.histogram_compare(list(range(24)), [("Sample of all accounts", real, ACCENT["people"]),
                                                 ("Verified humans", ver, ACCENT["timers"]),
                                                 ("Accounts with days shuffled", null, ACCENT["unclear"])],
                               "Length of the longest quiet stretch: real accounts, verified humans and shuffled accounts",
                               x_title="longest quiet stretch, hours")
    peak_real = max(range(24), key=lambda i: real[i])
    peak_ver = max(range(24), key=lambda i: ver[i])
    peak_null = max(range(24), key=lambda i: null[i])
    says = (f"Verified humans go quiet for about {peak_ver} hours at a stretch and accounts in general for about {peak_real}, close to a night's sleep. "
            f"The same accounts with each day randomly shifted around the clock peak at {peak_null}.")
    rows = [[g, full(cal["gap_real"][g]), full(v["gap_hist"][g]), full(cal["gap_null"][g])] for g in range(24)]
    return panel("chance", "Could the pattern be chance?", says, body, ["15_calibration.sql"],
                 C.table(["Longest quiet stretch (hours)", "Sample of all accounts", "Verified humans", "Days shuffled"], rows))


def fig_crosscheck(R):
    c = R["crosscheck"]
    days = c["daily"]
    labels = [d["date"][5:] for d in days]
    values = [d["bq_accounts"] for d in days]
    body = C.columns(labels, values, ACCENT["machines"], "Daily active accounts from the raw table, last 69 days",
                     height=240, x_every=10, x_title="", value_fmt=C.compact)
    says = (f"Plain counts from the raw BigQuery table match NearBlocks, a separate indexer, within 1% on all "
            f"{c['windows_within_1pct']} of {c['windows_compared']} windows and on {c['daily_tx_within_1pct']} of {c['daily_days']} days for transactions. "
            f"This chart is the raw daily active accounts for the last {c['daily_days']} days.")
    rows = [[d["date"], full(d["bq_tx"]), full(d["bq_accounts"]), full(d["bq_contracts"]), f"{d['tx_ratio']:.4f}", f"{d['acct_ratio']:.4f}"] for d in days]
    return panel("crosscheck", "Do the raw counts match an independent source?", says, body, ["10_daily_totals.sql"],
                 C.table(["Date", "Transactions", "Active accounts", "Contracts called", "Tx ratio to NearBlocks", "Accounts ratio"], rows))


def fig_timezones(R):
    tz = R["timezones"]["2026-10-01"]
    offs = list(range(-12, 12))
    total = tz["total"]
    shares = [v / total for v in tz["offset_counts"]]
    labels = [f"{o:+d}" for o in offs]
    body = C.columns(labels, shares, ACCENT["people"], "Where sleepers live by implied UTC offset, October 2026",
                     x_every=2, x_title="implied UTC offset (hours)", value_fmt=lambda v: f"{v * 100:.0f}%", tip_prefix="UTC ")
    top = sorted(zip(offs, shares), key=lambda x: -x[1])[:3]
    top_txt = ", ".join(f"UTC{o:+d}" for o, _ in top)
    says = f"A sleep midpoint hints at where someone lives. Today's sleepers cluster around {top_txt}. This describes the crowd, and nobody can be located precisely from it."
    rows = [[f"UTC{o:+d}", full(c)] for o, c in zip(offs, tz["offset_counts"])]
    return panel("timezones", "Where are they?", says, body, ["04_timezones.sql", "11_families.sql"],
                 C.table(["Implied UTC offset", "Sleepers"], rows))


def fig_dst(R):
    d = R["dst"]
    frame = C.Frame(height=220, left=210, right=40, top=16, bottom=44)
    x_min, x_max = -1.5, 1.5
    x = lambda v: frame.left + frame.plot_w * (v - x_min) / (x_max - x_min)
    events = [r for r in d["rows"] if r["direction"] != 0]
    n = len(events)
    row_h = frame.plot_h / n
    noise = d["placebo_sd"]
    frame.add(f'<rect x="{x(-noise):.1f}" y="{frame.top}" width="{x(noise) - x(-noise):.1f}" height="{frame.plot_h}" style="fill:var(--ink3);opacity:.14"/>')
    for v in (-1, 0, 1):
        frame.add(f'<line x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{frame.top}" y2="{frame.top + frame.plot_h}" class="grid"/>')
        frame.add(f'<text x="{x(v):.1f}" y="{frame.top + frame.plot_h + 18}" text-anchor="middle" class="axis">{v:+d} h</text>')
    frame.add(f'<text x="{x(1):.1f}" y="{frame.top + frame.plot_h + 36}" text-anchor="middle" class="axis">a full shift would land here</text>')
    labels = {"eu_spring_2026": "Europe, spring 2026", "us_spring_2026": "Americas, spring 2026", "eu_autumn_2026": "Europe, autumn 2026", "us_autumn_2026": "Americas, autumn 2026"}
    for i, row in enumerate(events):
        y = frame.top + row_h * (i + 0.5)
        name = labels[row["event"]]
        frame.add(f'<text x="{frame.left - 10}" y="{y + 4:.1f}" text-anchor="end" class="axis">{esc(name)}</text>')
        if row["region"] in row["shifts"] and "asia" in row["shifts"]:
            value = (row["shifts"][row["region"]] - row["shifts"]["asia"]) * row["direction"]
            frame.add(f'<circle cx="{x(value):.1f}" cy="{y:.1f}" r="5" class="dot" style="fill:var(--s-people)"/>')
            frame.add(f'<rect x="{frame.left}" y="{y - row_h / 2:.1f}" width="{frame.plot_w}" height="{row_h:.1f}" class="hit" data-tip="{C.tip(name, [("hours, compared with the expected direction", f"{value:+.1f}", "var(--s-people)")])}"/>')
    legend_txt = C.legend([("How far ordinary weeks drift on their own", "var(--ink3)", "box"), ("Each clock change: how far sleepers moved, compared with an Asian control group", "var(--s-people)", "box")])
    says = (f"When clocks change, people who observe daylight saving should move by an hour. Across {d['n_events']} clock changes the average move was "
            f"{d['mean_signed_effect']:+.2f} hours in the expected direction (95% interval {d['ci_low']:+.2f} to {d['ci_high']:+.2f}). "
            f"A full one-hour move is ruled out. Either few of these accounts live where clocks change, or they do not follow local time. This data cannot say which.")
    rows = [[labels.get(r["event"], r["event"]), r["date"], f"{r['shifts'].get('europe', float('nan')):+.1f}", f"{r['shifts'].get('americas', float('nan')):+.1f}",
             f"{r['shifts'].get('asia', float('nan')):+.1f}", f"{r['shifts'].get('machines', float('nan')):+.1f}"] for r in d["rows"]]
    return panel("dst", "Did they follow their clocks?", says, frame.svg("Daylight-saving shift per clock change") + legend_txt,
                 ["08_dst.sql"], C.table(["Event", "Date", "Europe group", "Americas group", "Asia control", "Machines"], rows))


def fig_sensitivity(R):
    s = R["sensitivity"]
    names = {
        "base": "As published", "alpha_01": "Stricter chance test (p below 0.01)", "hours_8": "Uses 8+ hours of the clock", "hours_10": "Uses 10+ hours of the clock",
        "gap_max_12": "Quiet stretch at most 12 hours", "gap_max_18": "Quiet stretch at most 18 hours",
        "days_6": "Active on 6+ days", "days_7": "Active on 7+ days", "no_chance_test": "No chance test at all",
    }
    rows = []
    for key, name in names.items():
        count = s[key]["count"]
        change = f"{s[key]['versus_base'] * 100:+.0f}%"
        if key in R["verified"]["variants"]:
            rows.append([name, full(count), change, pct(R["verified"]["variants"][key], 0), pct(R["calibration"]["variant_false_rates"][key], 1)])
        else:
            rows.append([name, full(count), change, "", ""])
    says = "Changing a rule moves the count a lot, which is one more reason to read it as a measurement of a behaviour and not as a head count."
    return panel("sensitivity", "How much depends on the rules?", says,
                 C.table(["Rule", "Accounts passing", "Change", "Verified humans passing", "Shuffled accounts passing"], rows),
                 ["06_sensitivity.sql"])


def changes_table(R):
    h = R["headline"]
    rel = R["relayed"]["2026-10-01"]
    rows = [
        ["Accounts passing the sleep test", full(h["humans"]), "above 25,000 for three windows in a row"],
        ["Named .near accounts that pass", full(h["humans_named"]), "above 3,000"],
        ["Share of those passing that are Telegram accounts", pct(h["telegram_share"], 0), "below 50%"],
        ["Accounts that pass only through relayers", full(rel["relayed_sleepers_not_counted_as_signers"]), "more than signers, three windows in a row"],
        ["Never-sleeping accounts' share of transactions", pct(h["machine_tx_share"], 0), "below 50% while transactions hold up"],
    ]
    return C.table(["Measure", "Today", "Would change my mind"], rows)


# ---- page ----------------------------------------------------------------------------

STYLE = """
:root {
  /* Layout: a night band holds the live check, then the evidence sits on day paper, one question per panel. */
  --paper: #edf1f7; --panel: #ffffff; --ink: #101830; --ink2: #47516d; --ink3: #6a7490; --rule: #d6dce8; --grid: #e7ebf2; --hover: rgba(42,120,214,.10);
  --night: #0f1835; --night2: #182353; --night-ink: #edf1fd; --night-ink2: #b4bedb; --night-rule: #2f3b6a; --tick: #f1f4ff; --moon: #ffd27a; --band: rgba(255,210,122,.16);
  --s-people: #2a78d6; --s-machines: #eb6834; --s-timers: #1baf7a; --s-unclear: #eda100;
  --good: #0ca30c; --bad: #d03b3b; --mid: #b98100;
  --display: "Bricolage Grotesque", "Avenir Next", "Segoe UI", sans-serif;
  --body: "Hanken Grotesk", "Segoe UI", system-ui, sans-serif;
  --mono: "Spline Sans Mono", ui-monospace, "Cascadia Code", Consolas, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --paper: #0b1124; --panel: #131b35; --ink: #e8edf9; --ink2: #b6c0da; --ink3: #8f9ab9; --rule: #2a3556; --grid: #222c4a; --hover: rgba(57,135,229,.16);
  --night: #070c1d; --night2: #10183a; --night-rule: #2a3560;
  --s-people: #3987e5; --s-machines: #d95926; --s-timers: #199e70; --s-unclear: #c98500;
  color-scheme: dark; } }
:root[data-theme="dark"] {
  --paper: #0b1124; --panel: #131b35; --ink: #e8edf9; --ink2: #b6c0da; --ink3: #8f9ab9; --rule: #2a3556; --grid: #222c4a; --hover: rgba(57,135,229,.16);
  --night: #070c1d; --night2: #10183a; --night-rule: #2a3560;
  --s-people: #3987e5; --s-machines: #d95926; --s-timers: #199e70; --s-unclear: #c98500;
  color-scheme: dark; }
* { box-sizing: border-box; }
[hidden] { display: none !important; }
body { background: var(--paper); color: var(--ink); font: 16px/1.55 var(--body); margin: 0; }
.wrap { max-width: 1040px; margin: 0 auto; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
h1, h2, h3 { font-family: var(--display); font-weight: 700; letter-spacing: -.01em; text-wrap: balance; margin: 0; }
a { color: inherit; }
header.night { background: var(--night); color: var(--night-ink); padding-block: 44px 40px; }
.brand { font: 500 13px/1 var(--mono); letter-spacing: .08em; color: var(--night-ink2); display: flex; align-items: center; gap: 10px; }
.brand svg { width: 16px; height: 16px; }
.hero { display: grid; grid-template-columns: minmax(0, 1fr); gap: 26px; }
.hero h1 { font-size: clamp(2.4rem, 7vw, 4.4rem); line-height: 1.02; margin-top: 18px; }
.lede { font-size: 1.16rem; color: var(--night-ink2); max-width: 44em; margin: 16px 0 0; }
.lede strong { color: var(--night-ink); font-weight: 600; }
.check { background: var(--night2); border-radius: 14px; padding: 20px; display: grid; gap: 14px; }
.check label { font-weight: 600; }
.check-row { display: flex; flex-wrap: wrap; gap: 10px; }
.check input { flex: 1 1 240px; min-width: 0; font: 15px var(--mono); padding: 11px 14px; border-radius: 9px; border: 1px solid var(--night-rule); background: var(--night); color: var(--night-ink); }
.check input::placeholder { color: var(--night-ink2); opacity: .7; }
.check input:focus-visible, button:focus-visible, summary:focus-visible, .try:focus-visible { outline: 2px solid var(--moon); outline-offset: 2px; }
button { font: 600 15px var(--body); }
.go { padding: 11px 20px; border-radius: 9px; border: 0; background: var(--moon); color: #161c33; cursor: pointer; }
.go:disabled { opacity: .55; cursor: wait; }
.tries { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 14px; color: var(--night-ink2); }
.try { font: 13px var(--mono); padding: 4px 9px; border-radius: 7px; border: 1px solid var(--night-rule); color: var(--night-ink); background: transparent; cursor: pointer; }
.try:hover { border-color: var(--moon); }
#check-status { font-size: 14px; color: var(--night-ink2); margin: 0; min-height: 1.4em; }
#check-status[data-state="error"] { color: #ffb4a8; }
.examples { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px; }
.ex { margin: 0; background: var(--night); border-radius: 12px; padding: 14px; display: grid; gap: 10px; align-content: start; }
.ex svg { width: 100%; height: auto; }
.ex figcaption { font-size: 14px; color: var(--night-ink2); }
.ex figcaption strong { color: var(--night-ink); }
.tick { fill: var(--tick); }
.sleep-band { fill: var(--band); }
.axis-night { font: 10px var(--mono); fill: var(--night-ink2); }
.rule-night { stroke: var(--night-rule); stroke-width: 1; }
.caption-night { font-size: 13px; color: var(--night-ink2); margin: 0; }
#result { background: var(--night); border-radius: 12px; padding: 16px; display: grid; gap: 16px; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr); align-items: start; border-left: 4px solid var(--moon); }
#result[hidden] { display: none; }
#result[data-tone="good"] { border-left-color: #54d38a; }
#result[data-tone="bad"] { border-left-color: #ff9172; }
#result[data-tone="mid"] { border-left-color: #ffd27a; }
#result svg { width: 100%; height: auto; }
.verdict { font: 700 1.7rem/1.1 var(--display); margin: 2px 0 6px; }
#result-account { font: 13px var(--mono); color: var(--night-ink2); }
#result-text { margin: 0 0 12px; color: var(--night-ink2); }
#result-facts { display: grid; grid-template-columns: 1fr auto; gap: 4px 14px; margin: 0 0 12px; font-size: 14px; }
#result-facts dt { color: var(--night-ink2); }
#result-facts dd { margin: 0; font: 13px var(--mono); text-align: right; }
.busy-note { display: grid; gap: 6px; padding: 18px 8px; }
.busy-note b { font: 700 2.4rem/1 var(--display); color: var(--night-ink); }
.busy-note span { color: var(--night-ink2); }
.link-btn { background: none; border: 0; padding: 0; color: var(--night-ink2); text-decoration: underline; cursor: pointer; font: 14px var(--body); }
main { padding-block: 34px 60px; display: grid; gap: 40px; }
section { display: grid; gap: 18px; }
h2 { font-size: clamp(1.6rem, 3.4vw, 2.2rem); }
.intro { color: var(--ink2); max-width: 42em; margin: 0; }
.tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.tile { background: var(--panel); border: 1px solid var(--rule); border-radius: 12px; padding: 16px; display: grid; gap: 4px; align-content: start; }
.tile-value { font: 700 clamp(1.8rem, 4.5vw, 2.5rem)/1.05 var(--display); }
.tile-label { font-weight: 600; font-size: 15px; }
.tile p { margin: 0; font-size: 14px; color: var(--ink2); }
.panel { background: var(--panel); border: 1px solid var(--rule); border-radius: 12px; padding: 20px; display: grid; gap: 10px; min-width: 0; }
.panel h3 { font-size: 1.3rem; }
.says { margin: 0; color: var(--ink2); max-width: 46em; }
.plot { overflow-x: auto; min-width: 0; }
.plot svg.chart { width: 100%; min-width: 620px; height: auto; display: block; }
.grid { stroke: var(--grid); stroke-width: 1; }
.axis { font: 11px var(--mono); fill: var(--ink3); }
.end { font: 600 12px var(--mono); fill: var(--ink); }
.line { fill: none; stroke-width: 2; stroke-linejoin: round; stroke-linecap: round; }
.dot { stroke: var(--panel); stroke-width: 2; }
.hit { fill: transparent; cursor: crosshair; }
.hit.on { fill: var(--hover); }
.legend { list-style: none; display: flex; flex-wrap: wrap; gap: 6px 18px; padding: 0; margin: 8px 0 0; font-size: 13px; color: var(--ink2); }
.legend li { display: flex; align-items: center; gap: 7px; }
.lg-line { width: 18px; height: 3px; border-radius: 2px; display: inline-block; }
.lg-box { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }
.rank { display: grid; gap: 7px; }
.rank-row { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 2fr) 72px; gap: 12px; align-items: center; font-size: 14px; }
.rank-name { font: 13px var(--mono); overflow-wrap: anywhere; }
.rank-bar { background: var(--grid); border-radius: 4px; height: 10px; overflow: hidden; }
.rank-bar span { display: block; height: 100%; border-radius: 4px; }
.rank-val { font: 13px var(--mono); text-align: right; }
.d { font-size: 14px; }
.d summary { cursor: pointer; color: var(--ink2); font-weight: 600; }
.file { font: 12px var(--mono); color: var(--ink3); margin: 10px 0 4px; }
pre { margin: 0; padding: 12px; background: var(--paper); border-radius: 8px; overflow-x: auto; font: 12.5px/1.5 var(--mono); }
.table-wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 14px; font-variant-numeric: tabular-nums; }
th { text-align: left; font-weight: 600; color: var(--ink2); border-bottom: 1px solid var(--rule); padding: 7px 10px; }
td { border-bottom: 1px solid var(--grid); padding: 7px 10px; }
td.num, th.num { text-align: right; font-family: var(--mono); font-size: 13px; }
.two { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
.model { display: grid; gap: 14px; }
.model label { font-weight: 600; display: block; margin-bottom: 4px; }
.model input[type=range] { width: 100%; }
.model .out { font: 600 14px var(--mono); color: var(--ink2); }
.model-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.mcell { background: var(--paper); border-radius: 10px; padding: 12px; }
.mcell b { display: block; font: 700 1.4rem/1.1 var(--display); }
.mcell span { font-size: 13px; color: var(--ink2); }
#model-verdict { margin: 0; color: var(--ink2); }
.note { font-size: 14px; color: var(--ink2); max-width: 46em; margin: 0; }
footer.page { border-top: 1px solid var(--rule); padding-block: 22px 34px; font-size: 14px; color: var(--ink2); }
.tip { position: fixed; left: 0; top: 0; z-index: 20; pointer-events: none; background: var(--ink); color: var(--panel); padding: 8px 10px; border-radius: 8px; font: 12px/1.4 var(--mono); max-width: 280px; display: grid; gap: 2px; }
.tip[hidden] { display: none; }
.tip-head { opacity: .75; }
.tip-key { display: inline-block; width: 12px; height: 3px; margin-right: 6px; vertical-align: middle; }
code.i { font: 13px var(--mono); background: var(--paper); padding: 1px 5px; border-radius: 5px; }
@media (max-width: 760px) {
  .examples, .tiles, .two, .model-grid { grid-template-columns: minmax(0, 1fr); }
  #result { grid-template-columns: minmax(0, 1fr); }
  .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (prefers-reduced-motion: no-preference) { html { scroll-behavior: smooth; } }
"""


def page(R):
    h = R["headline"]
    t = R["trend"]
    crit = contiguity.critical_gaps(config.ALPHA)
    payload = json.dumps({"crit": crit, "trend": {"latest": t["latest"], "peak": t["peak"]}})
    default_rate = max(-20, min(15, round(t["monthly_change"] * 100 * 2) / 2))
    core_js = (config.SITE / "src" / "sleep-core.js").read_text(encoding="utf-8")
    app_js = (config.SITE / "src" / "app.js").read_text(encoding="utf-8")

    body = f"""
<header class="night"><div class="wrap hero">
  <div>
    <div class="brand"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 15.5A8.5 8.5 0 0 1 8.5 4a8.5 8.5 0 1 0 11.5 11.5Z" fill="#ffd27a"/></svg>PROOF OF SLEEP</div>
    <h1>Humans sleep.<br>Machines don't.</h1>
    <p class="lede">{full(h["accounts"])} NEAR accounts were active in the first two weeks of October 2026. Only {full(h["regular_accounts"])} were active on at least 5 of those days. <strong>{full(h["humans"])}</strong> of them keep a sleep-sized quiet stretch the way a person does.</p>
  </div>
  <div class="check">
    <form id="check-form">
      <label for="check-account">Does this account sleep?</label>
      <div class="check-row" style="margin-top:8px">
        <input id="check-account" name="account" autocomplete="off" spellcheck="false" placeholder="yourname.near">
        <button class="go" id="check-button" type="submit">Check it</button>
      </div>
    </form>
    <div class="tries">Try: <button type="button" class="try" data-try="sweat-relayer.near">sweat-relayer.near</button><button type="button" class="try" data-try="relay.aurora">relay.aurora</button><button type="button" class="try" data-try="root.near">root.near</button></div>
    <p id="check-status" role="status"></p>
    <div id="result" hidden>
      <div id="result-chart"></div>
      <div>
        <div id="result-account"></div>
        <div class="verdict" id="result-title"></div>
        <p id="result-text"></p>
        <dl id="result-facts"></dl>
        <button type="button" class="link-btn" id="result-reset">Show the examples again</button>
      </div>
    </div>
    {examples_html()}
    <p class="caption-night">Three real accounts from NEAR, names removed. Each row is one day; each mark is an hour with at least one transaction, in UTC.</p>
  </div>
</div></header>
<div class="wrap"><main>

<section aria-labelledby="found"><h2 id="found">What the test found</h2>
<p class="intro">We took the first two weeks of every month since January 2021 and looked at when each account signs transactions. Over two weeks, an account passes if it uses at least {config.MIN_HOURS} different hours of the clock, never touches a stretch of {config.MIN_GAP} to {config.MAX_GAP} hours in a row, and that stretch is longer than chance would produce.</p>
{tiles(R)}</section>

<section aria-labelledby="people"><h2 id="people">The headline number is mostly not people</h2>
{fig_accounts(R)}
{fig_machines(R)}
</section>

<section aria-labelledby="works"><h2 id="works">Does the test work?</h2>
<p class="intro">These are checks on our own method, including the one that went against it.</p>
{fig_verified(R)}
{fig_range(R)}
{fig_gaps(R)}
{fig_dst(R)}
{fig_sensitivity(R)}
{fig_crosscheck(R)}
</section>

<section aria-labelledby="who"><h2 id="who">Who is left</h2>
{fig_families(R)}
{fig_apps(R)}
{fig_retention(R)}
{fig_timezones(R)}
</section>

<section aria-labelledby="where"><h2 id="where">Where the people went, and where value went</h2>
{fig_relayed(R)}
{fig_divergence(R)}
{fig_leadlag(R)}
</section>

<section aria-labelledby="ahead"><h2 id="ahead">What would have to happen</h2>
<article class="panel model" id="model">
  <h3>Try your own assumption about the next five years</h3>
  <p class="says">Over the last 12 windows the number of accounts passing the test has changed by {pct(t["monthly_change"])} a month, roughly halving every {t["half_life_months"]:.0f} months. Move the slider to see where it goes from {full(t["latest"])}.</p>
  <div><label for="model-rate">Monthly change in accounts passing</label><input type="range" id="model-rate" min="-20" max="15" step="0.5" value="{default_rate}"><span class="out" id="model-rate-out"></span></div>
  <div class="model-grid">
    <div class="mcell"><b id="model-1y">-</b><span>accounts in 1 year</span></div>
    <div class="mcell"><b id="model-3y">-</b><span>in 3 years</span></div>
    <div class="mcell"><b id="model-5y">-</b><span>in 5 years</span></div>
    <div class="mcell"><b id="model-needed">-</b><span>growth needed to reach the target below in 5 years</span></div>
  </div>
  <p id="model-verdict"></p>
  <div><label for="model-target">Target for 2031</label><input type="range" id="model-target" min="1000" max="150000" step="1000" value="25000"><span class="out" id="model-target-out"></span></div>
  <p class="note">This is arithmetic on one trend, not a forecast. It cannot tell you what a new app launch would do.</p>
</article>
<article class="panel" id="changes"><h3>What would change my mind</h3>
<p class="says">The full thesis is in THESIS.md. These are the numbers to watch.</p>{changes_table(R)}</article>
</section>

</main></div>
<footer class="page"><div class="wrap"><p>Built at NEAR HACKATHON. Code, queries and data: <a href="{esc(json.loads((config.ROOT / "data" / "links.json").read_text(encoding="utf-8"))["repo"])}">{esc(json.loads((config.ROOT / "data" / "links.json").read_text(encoding="utf-8"))["repo"])}</a></p>Source: the public NEAR dataset on BigQuery, the NEAR I-Am-Human registry, NearBlocks and DefiLlama. Every number on this page is rebuilt by one command from data in the repository. See README.md, METHOD.md and THESIS.md.</div></footer>
<script>window.PROOF = {payload};</script>
<script>{core_js}</script>
<script>{app_js}</script>
"""
    head = f"""<title>Proof of Sleep</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700&family=Hanken+Grotesk:wght@400;500;600&family=Spline+Sans+Mono:wght@400;500;600&display=swap">
<style>{STYLE}</style>"""
    return head, body


def test_page() -> str:
    core_js = (config.SITE / "src" / "sleep-core.js").read_text(encoding="utf-8")
    fixture = (config.ROOT / "tests" / "sql_fixture.json").read_text(encoding="utf-8")
    crit = json.dumps(contiguity.critical_gaps(config.ALPHA))
    return f"""<!doctype html><meta charset="utf-8"><title>sleep-core test</title><pre id="out">running</pre>
<script>{core_js}</script><script>
const FIX = {fixture}; const CRIT = {crit};
let bad = 0, n = 0;
for (const row of FIX) {{
  const g = SleepCore.classify(row.day_masks, CRIT); const w = row.expect; n++;
  if (g.class !== w.class || g.n_days !== w.n_days || g.n_hours !== w.n_hours || g.gap !== w.gap ||
      g.n_slots !== w.n_slots || Math.abs(g.mid - w.mid) > 1e-6) {{ bad++; console.log("MISMATCH", row, g); }}
}}
document.getElementById("out").textContent = (bad === 0 ? "PASS" : "FAIL") + " " + n + " accounts, " + bad + " mismatches";
window.TEST_RESULT = {{ n, bad }};
</script>"""


def main():
    R = json.loads((config.OUT / "results.json").read_text(encoding="utf-8"))
    head, body = page(R)
    standalone = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                  '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
                  + head + "</head><body>" + body + "</body></html>\n")
    (config.SITE / "index.html").write_text(standalone, encoding="utf-8", newline="\n")
    (config.SITE / "test.html").write_text(test_page(), encoding="utf-8", newline="\n")
    # A body-only version for preview hosts that add their own document skeleton
    (config.SITE / "embed.html").write_text(head + body, encoding="utf-8", newline="\n")
    return len(standalone)


if __name__ == "__main__":
    print(main())
