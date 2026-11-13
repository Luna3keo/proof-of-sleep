-- How much does the count depend on the thresholds? Recounts sleepers under other choices,
-- changing one rule at a time. Uses the table from step 0, so it costs almost nothing.
WITH t AS (
  SELECT window_start, n_days, n_slots, n_hours, gap, {crit_05}[OFFSET(n_hours)] AS c05, {crit_01}[OFFSET(n_hours)] AS c01
  FROM `{project}.{dataset}.account_windows`
  WHERE account != '_light_'
)
SELECT
  window_start,
  COUNTIF(n_days >= 5 AND n_hours >= 6 AND gap BETWEEN 5 AND 14 AND gap >= c05) AS base,
  COUNTIF(n_days >= 5 AND n_hours >= 6 AND gap BETWEEN 5 AND 14 AND gap >= c01) AS alpha_01,
  COUNTIF(n_days >= 5 AND n_hours >= 4 AND gap BETWEEN 5 AND 14 AND gap >= c05) AS hours_4,
  COUNTIF(n_days >= 5 AND n_hours >= 8 AND gap BETWEEN 5 AND 14 AND gap >= c05) AS hours_8,
  COUNTIF(n_days >= 5 AND n_hours >= 10 AND gap BETWEEN 5 AND 14 AND gap >= c05) AS hours_10,
  COUNTIF(n_days >= 5 AND n_hours >= 6 AND gap BETWEEN 5 AND 12 AND gap >= c05) AS gap_max_12,
  COUNTIF(n_days >= 5 AND n_hours >= 6 AND gap BETWEEN 5 AND 18 AND gap >= c05) AS gap_max_18,
  COUNTIF(n_days >= 4 AND n_hours >= 6 AND gap BETWEEN 5 AND 14 AND gap >= c05) AS days_4,
  COUNTIF(n_days >= 6 AND n_hours >= 6 AND gap BETWEEN 5 AND 14 AND gap >= c05) AS days_6,
  COUNTIF(n_days >= 7 AND n_hours >= 6 AND gap BETWEEN 5 AND 14 AND gap >= c05) AS days_7,
  COUNTIF(n_days >= 5 AND n_hours >= 6 AND gap BETWEEN 5 AND 14) AS no_chance_test
FROM t
WHERE n_hours IS NOT NULL
GROUP BY 1
ORDER BY 1
