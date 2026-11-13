-- What do people on NEAR use? For a set of sample windows: per contract, how many
-- sleepers and how many machines call it, and how many transactions each sends.
WITH tx AS (
  SELECT
    DATE_TRUNC(block_date, MONTH) AS window_start,
    signer_account_id AS account,
    receiver_account_id AS contract,
    COUNT(*) AS n
  FROM `{source}.transactions`
  WHERE {app_filter}
  GROUP BY 1, 2, 3
),
joined AS (
  SELECT t.window_start, t.contract, t.account, t.n, COALESCE(a.class, 'light') AS class
  FROM tx AS t
  LEFT JOIN `{project}.{dataset}.account_windows` AS a
    ON a.account = t.account AND a.window_start = t.window_start
),
per_contract AS (
  SELECT
    window_start, contract,
    COUNT(*) AS signers,
    SUM(n) AS txs,
    COUNTIF(class = 'sleeper') AS sleepers,
    SUM(IF(class = 'sleeper', n, 0)) AS sleeper_txs,
    COUNTIF(class = 'machine') AS machines,
    SUM(IF(class = 'machine', n, 0)) AS machine_txs
  FROM joined
  GROUP BY 1, 2
),
ranked AS (
  SELECT *,
    ROW_NUMBER() OVER (PARTITION BY window_start ORDER BY sleepers DESC, contract) AS by_sleepers,
    ROW_NUMBER() OVER (PARTITION BY window_start ORDER BY txs DESC, contract) AS by_txs
  FROM per_contract
)
SELECT window_start, contract, signers, txs, sleepers, sleeper_txs, machines, machine_txs, by_sleepers, by_txs
FROM ranked
WHERE (by_sleepers <= 40 OR by_txs <= 40)
  AND NOT REGEXP_CONTAINS(contract, r'^[^.]+\.tg$')   -- a bare .tg name is a person's account, not an app
ORDER BY window_start, by_sleepers
