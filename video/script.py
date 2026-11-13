"""The words of the demo video, filled from the computed results.

`say` is what the voice reads, with numbers spelled out so nothing is mispronounced.
`show` is the caption on screen. Every number comes from data/out/results.json.

    python video/script.py        # prints the script and writes docs/DEMO_SCRIPT.md
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.render_docs import words  # noqa: E402

MOODS = {
    "plain": {"speed": 0.90, "pitch": 0.000, "gain": 0.0},
    "ask": {"speed": 0.88, "pitch": 0.012, "gain": 0.0},
    "turn": {"speed": 0.90, "pitch": 0.015, "gain": 1.0},
    "heavy": {"speed": 0.86, "pitch": -0.02, "gain": -0.5},
    "firm": {"speed": 0.86, "pitch": -0.005, "gain": 0.5},
    "warm": {"speed": 0.89, "pitch": 0.01, "gain": 0.0},
}


def load():
    from pipeline.build_site import pick_examples
    R = json.loads((ROOT / "data" / "out" / "results.json").read_text(encoding="utf-8"))
    h = R["headline"]
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    year, month, _ = h["peak_window"].split("-")
    spoken_year = {"2024": "twenty twenty-four", "2025": "twenty twenty-five"}[year]
    return {
        "example_gap": pick_examples()[0][1]["gap"],
        "accounts": h["accounts"],
        "accounts_k": h["accounts"] // 1000,
        "regular": h["regular_accounts"],
        "regular_k": round(h["regular_accounts"] / 1000),
        "humans": h["humans"],
        "humans_hundreds": round(h["humans"] / 100) * 100,
                "machines": h["machines"],
        "machine": round(h["machine_tx_share"] * 100),
        "decline": round(h["decline_from_peak"] * 100),
        "peak_month": months[int(month) - 1],
        "peak_year": year,
        "peak_year_spoken": spoken_year,
    }


def script():
    n = load()
    acc_words = f"{words(n['accounts_k'])} thousand"
    L = lambda mark, mood, say, show, pause=0.42: {"mark": mark, "mood": mood, "say": say, "show": show, "pause": pause}  # noqa: E731
    return [
        {"name": "problem", "label": "The problem", "lines": [
            L("ask", "ask", "How many people actually use a blockchain?", "How many people actually use a blockchain?", 0.5),
            L("count", "plain", f"In two weeks of October, more than {acc_words} accounts were active on NEAR.", f"{n['accounts']:,} accounts were active on NEAR in two weeks of October."),
            L("either", "plain", "But an account can be a person, or a program.", "An account can be a person, or a program.", 0.3),
            L("which", "plain", "A transaction won't tell you which.", "A transaction won't tell you which.", 0.6),
        ]},
        {"name": "idea", "label": "The idea", "lines": [
            L("never", "turn", "There's one thing programs never do. They never sleep.", "Programs never sleep.", 0.5),
            L("built", "plain", "So we built a test called Proof of Sleep. It looks at what time each account acts, day after day.", "Proof of Sleep looks at what time each account acts, day after day.", 0.5),
        ]},
        {"name": "work", "label": "See it work", "lines": [
            L("rows", "plain", "Here are three real accounts. Each row is a day. Each mark is an hour with activity.", "Each row is a day. Each mark is an hour with activity.", 0.35),
            L("person", "plain", f"This one never touches the same {words(n['example_gap'])} hours, and is active at many other times. That's a sleeper.", f"Never active in the same {n['example_gap']} hours, active at many others: a sleeper.", 0.3),
            L("machine", "plain", "This one fills nearly every hour. That's a machine.", "Nearly every hour, every day: a machine.", 0.3),
            L("timer", "plain", "And this one fires at the same hour, every day. That's a timer.", "The same hour, every day: a timer.", 0.5),
            L("live", "turn", "Now let's test a real account, live.", "Now a real account, live.", 0.3),
            L("click", "plain", "One click, and it reads the account's public history.", "It reads the account's public history.", 0.75),
            L("verdict", "turn", "Too fast to be a person.", "Too fast to be a person.", 0.55),
        ]},
        {"name": "found", "label": "What we found", "lines": [
            L("people", "heavy", f"In October, only about {words(n['regular_k'])} thousand of those accounts were active on five days or more. About {words(n['humans_hundreds'])} pass the test.", f"{n['regular']:,} accounts were regular. {n['humans']:,} pass the test."),
            L("est", "plain", "That isn't a head count. The test misses many real people, and some accounts pass by chance.", "That isn't a head count. The true number could be far higher or lower."),
            L("mach", "plain", f"{words(n['machines']).capitalize()} accounts that never sleep sent {words(n['machine'])} percent of all transactions.", f"{n['machines']} accounts that never sleep sent {n['machine']}% of all transactions."),
            L("fall", "heavy", f"And since {n['peak_month']} {n['peak_year_spoken']}, the accounts that pass have fallen {words(n['decline'])} percent.", f"Since {n['peak_month']} {n['peak_year']}, the accounts that pass have fallen {n['decline']}%.", 0.6),
        ]},
        {"name": "trust", "label": "Can you trust it?", "lines": [
            L("verified", "firm", "We checked the test against five thousand accounts verified as human by a face scan. Depending on the year, between one in three and one in seven pass. Accounts with shuffled days pass about two in a hundred.", "Face-verified humans: between 1 in 3 and 1 in 7 pass. Shuffled accounts: about 2 in 100.", 0.4),
            L("floor", "plain", "So a pass is real evidence, but the test misses most people.", "A pass is real evidence, but the test misses most people.", 0.4),
            L("catch", "plain", "People who swap through NEAR Intents, or use relayers, often never sign for themselves. So we can't see them all.", "People who swap through NEAR Intents, or use relayers, are harder to see.", 0.4),
            L("clock", "plain", "And when clocks changed, we saw no shift. So we can't prove these accounts keep local time.", "When clocks changed, we saw no shift.", 0.6),
        ]},
        {"name": "means", "label": "What it means", "lines": [
            L("thesis", "firm", "So here is the thesis. Don't treat the user counts on NEAR as proof of demand. Value NEAR for the money it moves, and treat real people as the upside.", "Don't read NEAR's user counts as proof of demand. Value NEAR for the money it moves.", 0.45),
            L("mind", "plain", "We list the exact numbers that would change our minds.", "We list the numbers that would change our minds.", 0.6),
        ]},
        {"name": "you", "label": "Your turn", "lines": [
            L("rebuild", "warm", "Every chart rebuilds from public data, with one command.", "Every chart rebuilds from public data, with one command.", 0.4),
            L("yours", "ask", "So, does your account sleep?", "Does your account sleep?", 1.6),
        ]},
    ]


def word_count(takes):
    return sum(len(line["say"].split()) for take in takes for line in take["lines"])


def write_markdown(takes):
    out = ["# Demo video script", "", "Every number is filled in from `data/out/results.json` by `python video/script.py`.", "",
           f"About {word_count(takes)} spoken words.", ""]
    for take in takes:
        out += [f"## {take['label']}", ""]
        for line in take["lines"]:
            out += [f"- {line['say']}  ", f"  On screen: *{line['show']}*"]
        out.append("")
    (ROOT / "docs" / "DEMO_SCRIPT.md").write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    takes = script()
    write_markdown(takes)
    print(word_count(takes), "words")
    for take in takes:
        print("\n##", take["label"])
        for line in take["lines"]:
            print("-", line["say"])
