# Submission checklist

Nothing has been sent. The rules in HACKATHON.md say the person submitting must confirm the exact payload first, and that a saved submission cannot be edited. Read the live HACKATHON.md again just before submitting.

## You must supply these. They were not guessed.

| Field | Rule | Value |
| --- | --- | --- |
| Project name | 2-80 characters | Proof of Sleep |
| Team lead's name | 2-80 characters | *yours* |
| Contact email | 160 characters at most | *yours* |
| Team size | `1`, `2 - 4`, `4 - 6`, `6 - 8` or `8+` | *yours* |
| NEAR payout account | a mainnet account you control | *yours* |
| Repository URL | public, submitted only once | https://github.com/Luna3keo/proof-of-sleep |
| Demo post URL | your public X post | *after posting* |
| Consent | "I agree that the organizers may use these details to review our submission and contact us about this hackathon." | *you must agree* |

Tracks: `thesis`.

## What they built (834 characters, limit 2000)

```text
NEAR's active-account and transaction counts are often read as proof of real demand, but nobody can say how many of those accounts are people. Proof of Sleep tests every account's daily rhythm on public NEAR data, because people sleep and machines do not, and it checks the test against 5,014 NEAR accounts verified as human by a face scan. Of 748,667 accounts active in two weeks of October 2026, 5,771 pass, and 340 accounts that never sleep sent 74% of all transactions. The result is an investment thesis with its evidence for and against, a dashboard that shows every chart's query, a live check of any NEAR account, and one command that rebuilds every number. NEAR makes this possible because every account's full history is public in its BigQuery dataset, and its on-chain I-Am-Human registry gives real people to test against.
```

## Before you send

- [ ] Repository is public with no secrets in its history (`.env` is ignored by git)
- [ ] `python rebuild.py --check` passes on a fresh clone
- [ ] Dashboard is hosted, and the live check works there
- [ ] X post is live with the video attached
- [ ] Payload shown to you and confirmed
