-- Humans who never sign. When a relayer pays gas for someone, the relayer signs the transaction
-- and the person only appears as the receiver of a DELEGATE_ACTION. This runs the same sleep test
-- on those people, for the windows in {relayed_windows}.
WITH acted AS (
  SELECT
    DATE_TRUNC(block_date, MONTH) AS window_start,
    receipt_receiver_account_id AS account,
    block_date,
    EXTRACT(HOUR FROM block_timestamp_utc) AS hour,
    COUNT(*) AS n
  FROM `{source}.receipt_actions`
  WHERE ({relayed_filter}) AND action_kind = 'DELEGATE_ACTION'
  GROUP BY 1, 2, 3, 4
),
days AS (
  SELECT window_start, account, block_date, SUM(n) AS n, COUNT(*) AS n_slots, BIT_OR(1 << hour) AS day_mask
  FROM acted
  GROUP BY 1, 2, 3
),
accounts AS (
  SELECT window_start, account, SUM(n) AS n, COUNT(*) AS n_days, SUM(n_slots) AS n_slots, BIT_OR(day_mask) AS hour_mask
  FROM days
  GROUP BY 1, 2
),
hours AS (
  SELECT *, ARRAY(SELECT h FROM UNNEST(GENERATE_ARRAY(0, 23)) AS h WHERE (hour_mask >> h) & 1 = 1) AS hs
  FROM accounts
),
gaps AS (
  SELECT *,
    (SELECT AS STRUCT gap, start_h FROM (
       SELECT h AS start_h,
              COALESCE((SELECT MIN(h2) FROM UNNEST(hs) AS h2 WHERE h2 > h), hs[OFFSET(0)] + 24) - h - 1 AS gap
       FROM UNNEST(hs) AS h) ORDER BY gap DESC, start_h LIMIT 1) AS g
  FROM hours
),
classified AS (
  SELECT window_start, account, n, {class_case_inline} AS relayed_class
  FROM gaps
)
SELECT
  c.window_start,
  c.relayed_class,
  COALESCE(w.class, 'no_signed_txs') AS signer_class,
  COUNT(*) AS accounts,
  SUM(c.n) AS delegate_actions
FROM classified AS c
LEFT JOIN `{project}.{dataset}.account_windows` AS w
  ON w.account = c.account AND w.window_start = c.window_start
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3
