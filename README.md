# Proof of Sleep

An entry for NEAR HACKATHON, track **Investment Thesis** (`thesis`). Built at NEAR HACKATHON.

- **Live dashboard:** https://luna3keo.github.io/proof-of-sleep/
- **Demo video:** [media/demo.mp4](media/demo.mp4) (138 seconds)
- **Thesis:** [THESIS.md](THESIS.md)

Humans sleep and machines do not. This project measures which NEAR accounts go quiet every day the way a sleeping person does, and uses that to ask how much of NEAR's reported usage is people.

## The problem

NEAR's headline activity numbers are often used as evidence of real demand. In 1-14 October 2026, 748,667 accounts were active. An investor needs to know how many of those are people, and there has been no reproducible way to say.

## What this project is

- **A statistical test** that labels an account as sleeping, never sleeping, on a timer, on a narrow routine, unclear, or too quiet to judge, using only when it signs transactions.
- **An outside check** of that test against 5,014 NEAR accounts verified as human by a face scan.
- **A thesis**, [THESIS.md](THESIS.md), with the claim, the evidence for it, the evidence against it, and what would change my mind.
- **A static dashboard**, `site/index.html`: each chart, the query behind it and one plain sentence, plus a live check of any account.
- **A rebuild command** that produces every chart and number from raw data.

## Result in one paragraph

Of 748,667 accounts active in 1-14 October 2026, 61,957 were active on at least 5 of the 14 days, and 5,771 of those pass the sleep test. That is not a head count: the test misses most verified humans and some accounts pass by chance, so the true number of regular people could be anywhere from about 1,200 to about 34,400. 340 accounts that never sleep sent 74% of all transactions. The count passing the test is down 95% since June 2024. The thesis: value NEAR as settlement infrastructure run by machines, and treat consumer adoption as something the data does not yet show. The evidence against this view is in [THESIS.md](THESIS.md) too.

## Try it

Needs Python 3.10 or newer. No packages to install, no keys.

1. Clone the repository and `cd` into it.
2. Run `python -m unittest discover -s tests`. You should see `OK` at the end. The tests prove the Python and the BigQuery SQL give identical results on 900 real accounts (names removed).
3. Run `python rebuild.py --check`. You should see the key numbers (for example `people 5,771`), then `MATCH: results reproduce the published hash`. This rebuilds every chart, table, THESIS.md, METHOD.md and this README from `data/raw/`.
4. Open the live dashboard at https://luna3keo.github.io/proof-of-sleep/, or `site/index.html` from your clone. You should see three example accounts, then the charts, each with its query and one plain sentence.
5. In the "Does this account sleep?" box, click `sweat-relayer.near`. Within a few seconds you should see a verdict such as "Too fast to be a person", computed in your browser from public chain data. Type your own account to test it.
6. Open `site/test.html`. You should see `PASS 900 accounts, 0 mismatches`. This confirms the JavaScript used for the live check gives the same answers as the Python and the SQL.
7. To re-run a query yourself, run `python -m pipeline.pull_bigquery --print 10` and paste the SQL into the BigQuery console. Results match `data/raw/daily_totals.csv`. Steps 10 and 15 run on their own; the others read the table built by step 00.

To rebuild from the chain itself rather than the committed CSV files:

1. Create a Google Cloud project (the free BigQuery sandbox is enough) and run `gcloud auth login`.
2. Copy `.env.example` to `.env` and set `BQ_PROJECT` to your project.
3. Run `python rebuild.py --from-bigquery`. It reads about 132 GB in total, inside the free 1 TiB a month, and every statement has a byte cap.

## What the numbers say

| Measure, 1-14 October 2026 | Value |
| --- | --- |
| Active accounts | 748,667 |
| Of which seen on only 1 or 2 days | 668,994 |
| Active on at least 5 of 14 days | 61,957 |
| Passed the sleep test | 5,771 |
| Plausible range of regular people | 1,200 to 34,400 |
| Also pass when counted through relayers | 4,203 |
| Accounts that never sleep | 340 |
| Their share of transactions | 74% |
| Busiest 100 accounts that are machines | 99 |
| Face-verified human account-windows that pass | 25% |
| Shuffled accounts that pass | 1.9% |
| Agreement with NearBlocks, within 1% | 70 of 70 windows |

## How NEAR is used

NEAR is the subject of the analysis rather than a dependency. The data is mainnet transactions from the NEAR public BigQuery dataset, and the outside check uses NEAR's on-chain I-Am-Human registry. The live check uses FastNEAR's public index. This project writes nothing on chain, needs no account and spends no tokens.

## Repository map

| Path | What it is |
| --- | --- |
| `THESIS.md` | the investment thesis |
| `METHOD.md` | definitions, tests, limits, corrections |
| `rebuild.py` | one command: rebuild every chart and number |
| `sql/` | every BigQuery query, each behind a chart |
| `pipeline/` | data pulls, the sleep test in Python, analysis, site builder |
| `data/raw/` | query results (aggregates only) |
| `data/out/results.json` | every number used anywhere |
| `site/index.html` | the dashboard |
| `site/test.html` | checks the browser test against the fixture |
| `tests/` | unit tests and the SQL fixture |
| `video/` | how the demo video was made |
| `docs/` | demo script, X post draft, submission draft |

## Disclosures

- **Built with an AI coding agent** (Claude Code). All work was done during the hackathon window.
- **Libraries:** Python standard library only. The dashboard loads three Google Fonts and has no JavaScript dependencies. The demo video was made with Kokoro text-to-speech, headless Microsoft Edge and FFmpeg.
- **NEAR Intents Explorer API:** the track's starter prompt suggests it. This project uses DefiLlama's public volume series, because the Explorer needs a partner token and its terms restrict keeping the data. `pipeline/pull_intents_explorer.py` is included for anyone who has a token, and it has not been run against the live API.

## License

MIT. See [LICENSE](LICENSE).
