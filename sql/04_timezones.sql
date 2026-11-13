-- Where sleepers are on the clock: the UTC hour at the middle of each sleeper's quiet stretch.
-- Rounded down to the hour. Aggregate counts only, never individual accounts.
SELECT
  window_start,
  CAST(FLOOR(mid) AS INT64) AS mid_hour_utc,
  COUNT(*) AS sleepers
FROM `{project}.{dataset}.account_windows`
WHERE class = 'sleeper'
GROUP BY 1, 2
ORDER BY 1, 2
