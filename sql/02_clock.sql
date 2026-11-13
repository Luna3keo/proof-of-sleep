-- For each class and each hour of the day (UTC): how many accounts were ever active in that hour.
-- Accounts seen on 1-2 days are not included (the class needs at least 3 active days).
SELECT
  window_start,
  class,
  hour,
  COUNTIF((hour_mask >> hour) & 1 = 1) AS accounts
FROM `{project}.{dataset}.account_windows`, UNNEST(GENERATE_ARRAY(0, 23)) AS hour
WHERE account != '_light_'
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3
