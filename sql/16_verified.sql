-- Outside check. {verified_count} accounts were verified as unique humans by a face scan
-- (NEAR's I-Am-Human soulbound tokens, issuer fractal.i-am-human.near). How do they score?
-- Output is counts by feature, never individual accounts.
SELECT
  window_start,
  gap,
  n_hours,
  n_days,
  n_slots,
  class,
  COUNT(*) AS account_windows
FROM `{project}.{dataset}.account_windows`
WHERE account IN UNNEST({verified_list}) AND n_days >= {min_days}
GROUP BY 1, 2, 3, 4, 5, 6
ORDER BY 1, 2, 3, 4, 5, 6
