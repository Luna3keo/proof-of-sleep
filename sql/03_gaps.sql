-- Distribution of the longest daily quiet stretch, for accounts active on at least 5 of 14 days.
SELECT
  window_start,
  gap,
  COUNT(*) AS accounts
FROM `{project}.{dataset}.account_windows`
WHERE account != '_light_' AND n_days >= {min_days}
GROUP BY 1, 2
ORDER BY 1, 2
