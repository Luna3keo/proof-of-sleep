-- Headline table: how many accounts fall in each class in each 14-day window,
-- and how many transactions each class sent.
SELECT
  window_start,
  class,
  SUM(accounts) AS accounts,
  SUM(n_tx) AS txs
FROM `{project}.{dataset}.account_windows`
GROUP BY 1, 2
ORDER BY 1, 2
