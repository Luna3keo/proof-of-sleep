-- How concentrated are transactions? Share of each window's transactions sent by the
-- busiest accounts. Aggregate counts only.
WITH ranked AS (
  SELECT
    window_start,
    n_tx,
    class,
    ROW_NUMBER() OVER (PARTITION BY window_start ORDER BY n_tx DESC, account) AS rnk
  FROM `{project}.{dataset}.account_windows`
  WHERE account != '_light_'
)
SELECT
  window_start,
  SUM(n_tx) AS txs_in_table,
  SUM(IF(rnk <= 10, n_tx, 0)) AS top_10,
  SUM(IF(rnk <= 100, n_tx, 0)) AS top_100,
  SUM(IF(rnk <= 1000, n_tx, 0)) AS top_1000,
  COUNTIF(rnk <= 100 AND class = 'machine') AS top100_machines,
  COUNTIF(rnk <= 100 AND class = 'sleeper') AS top100_sleepers
FROM ranked
GROUP BY 1
ORDER BY 1
