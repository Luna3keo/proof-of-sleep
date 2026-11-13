-- Do accounts come back? For every window and class: of the accounts in that class,
-- how many are seen again (on at least 3 days) 1, 3, 6 and 12 months later.
WITH a AS (
  SELECT account, window_start, class
  FROM `{project}.{dataset}.account_windows`
  WHERE account != '_light_'
),
later AS (
  SELECT account, window_start AS later_start, class AS later_class
  FROM `{project}.{dataset}.account_windows`
  WHERE account != '_light_'
)
SELECT
  a.window_start,
  a.class,
  m AS months_later,
  COUNT(DISTINCT a.account) AS cohort,
  COUNT(DISTINCT later.account) AS seen_again,
  COUNT(DISTINCT IF(later.later_class = 'sleeper', later.account, NULL)) AS seen_again_sleeping
FROM a
CROSS JOIN UNNEST([1, 3, 6, 12]) AS m
LEFT JOIN later
  ON later.account = a.account
  AND later.later_start = DATE_ADD(a.window_start, INTERVAL m MONTH)
WHERE DATE_ADD(a.window_start, INTERVAL m MONTH) <= DATE '2026-10-01'
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3
