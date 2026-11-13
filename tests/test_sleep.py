"""Run:  python -m unittest discover -s tests -v

No network, no BigQuery, no packages to install.
"""
import itertools
import json
import pathlib
import random
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import contiguity, sleep  # noqa: E402


def mask(*hours):
    value = 0
    for hour in hours:
        value |= 1 << hour
    return value


class LongestQuiet(unittest.TestCase):
    def test_wraps_past_midnight(self):
        # active 07:00-22:00 every hour: quiet from 23:00 through 06:00 = 8 hours
        gap, mid = sleep.longest_quiet(mask(*range(7, 23)))
        self.assertEqual(gap, 8)
        self.assertAlmostEqual(mid, 3.0)

    def test_all_hours_active(self):
        self.assertEqual(sleep.longest_quiet(mask(*range(24)))[0], 0)

    def test_single_hour(self):
        self.assertEqual(sleep.longest_quiet(mask(12))[0], 23)


class Contiguity(unittest.TestCase):
    def brute(self, m, gap):
        count = hit = 0
        for combo in itertools.combinations(range(24), m):
            count += 1
            if sleep.longest_quiet(mask(*combo))[0] >= gap:
                hit += 1
        return hit / count

    def test_exact_formula_matches_brute_force(self):
        for m, gap in ((1, 20), (2, 15), (3, 10), (4, 8), (5, 9), (6, 8)):
            self.assertAlmostEqual(contiguity.p_quiet_at_least(m, gap), self.brute(m, gap), places=9)

    def test_critical_gap_is_the_shortest_that_passes(self):
        crit = contiguity.critical_gaps(0.05)
        for m in range(4, 20):
            if crit[m] < 99:
                self.assertLessEqual(contiguity.p_quiet_at_least(m, crit[m]), 0.05)
                self.assertGreater(contiguity.p_quiet_at_least(m, crit[m] - 1), 0.05)


class Classify(unittest.TestCase):
    def test_person_like_account_sleeps(self):
        days = [mask(8 + (i % 3), 13, 18 + (i % 4), 21) for i in range(12)]
        days += [mask(7, 22), mask(23, 12)]
        self.assertEqual(sleep.classify(days)["class"], "sleeper")

    def test_relayer_never_sleeps(self):
        days = [mask(*range(24)) for _ in range(14)]
        self.assertEqual(sleep.classify(days)["class"], "machine")

    def test_all_hours_used_but_lightly_is_not_a_machine(self):
        # a different single hour each day: the union covers the clock, yet each day is light
        days = [mask(h) for h in range(0, 24, 2)] + [mask(h) for h in range(1, 24, 2)]
        result = sleep.classify(days)
        self.assertLess(result["gap"], 3)
        self.assertNotEqual(result["class"], "machine")

    def test_cron_job_is_a_timer(self):
        self.assertEqual(sleep.classify([mask(4)] * 14)["class"], "timer")

    def test_narrow_daily_habit_is_a_routine_not_a_sleeper(self):
        # always within the same few evening hours
        days = [mask(19 + (i % 5)) for i in range(14)]
        result = sleep.classify(days)
        self.assertEqual(result["n_hours"], 5)
        self.assertEqual(result["class"], "routine")

    def test_too_few_days_cannot_be_judged(self):
        self.assertEqual(sleep.classify([mask(9, 12, 18), mask(10, 20)])["class"], "too_few")

    def test_random_hours_rarely_pass(self):
        rng = random.Random(5)
        passed = 0
        for _ in range(2000):
            days = [mask(*rng.sample(range(24), 3)) for _ in range(10)]
            passed += sleep.classify(days)["class"] == "sleeper"
        self.assertLess(passed / 2000, 0.05)


class Rotate(unittest.TestCase):
    def test_keeps_shape(self):
        self.assertEqual(bin(sleep.rotate(mask(1, 2, 3), 7)).count("1"), 3)

    def test_wraps(self):
        self.assertEqual(sleep.rotate(mask(23), 1), mask(0))


class SqlMatchesPython(unittest.TestCase):
    """900 real accounts: the numbers BigQuery computed must equal this file's logic exactly."""

    def test_fixture(self):
        data = json.loads((ROOT / "tests" / "sql_fixture.json").read_text())
        self.assertGreater(len(data), 500)
        for row in data:
            got = sleep.classify(row["day_masks"])
            want = row["expect"]
            for key in ("class", "n_days", "n_slots", "n_hours", "gap"):
                self.assertEqual(got[key], want[key])
            self.assertAlmostEqual(got["mid"], want["mid"], places=6)


if __name__ == "__main__":
    unittest.main()
