-- Step 0. One row per account per 14-day window, with its daily rhythm features.
-- Everything else reads this table, so the expensive scan of `transactions` happens once.
-- The filter on block_date is literal: only the sampled days are read and billed.
-- Not partitioned by date on purpose: BigQuery's free tier deletes date partitions older than 60 days.
CREATE OR REPLACE TABLE `{project}.{dataset}.account_windows`
CLUSTER BY window_start, class AS
WITH slots AS (                             -- one row per account, day and hour with activity
  SELECT
    signer_account_id AS account,
    DATE_TRUNC(block_date, MONTH) AS window_start,
    block_date,
    EXTRACT(HOUR FROM block_timestamp_utc) AS hour,
    COUNT(*) AS n_tx
  FROM `{source}.transactions`
  WHERE {window_filter}
  GROUP BY 1, 2, 3, 4
),
days AS (                                   -- which hours each active day used
  SELECT
    account, window_start, block_date,
    SUM(n_tx) AS n_tx,
    COUNT(*) AS n_slots,
    BIT_OR(1 << hour) AS day_mask
  FROM slots
  GROUP BY 1, 2, 3
),
accounts AS (                               -- all the hours of the clock the account ever used
  SELECT
    account, window_start,
    SUM(n_tx) AS n_tx,
    COUNT(*) AS n_days,
    SUM(n_slots) AS n_slots,
    BIT_OR(day_mask) AS hour_mask
  FROM days
  GROUP BY 1, 2
),
hours AS (
  SELECT *, ARRAY(SELECT h FROM UNNEST(GENERATE_ARRAY(0, 23)) AS h WHERE (hour_mask >> h) & 1 = 1) AS hs
  FROM accounts
),
gaps AS (                                   -- the longest stretch of hours never used, wrapping past midnight
  SELECT *,
    (SELECT AS STRUCT gap, start_h
     FROM (
       SELECT h AS start_h,
              COALESCE((SELECT MIN(h2) FROM UNNEST(hs) AS h2 WHERE h2 > h), hs[OFFSET(0)] + 24) - h - 1 AS gap
       FROM UNNEST(hs) AS h
     )
     ORDER BY gap DESC, start_h
     LIMIT 1) AS g
  FROM hours
),
classified AS (
  SELECT
    account, window_start, n_tx, n_days, n_slots, hour_mask,
    ARRAY_LENGTH(hs) AS n_hours,
    g.gap AS gap,
    -- middle of the quiet stretch, as a clock hour (UTC)
    (g.start_h + 1 + g.gap / 2) - 24 * FLOOR((g.start_h + 1 + g.gap / 2) / 24) AS mid,
    {class_case_inline} AS class
  FROM gaps
)
SELECT                                      -- accounts seen on 1-2 days are kept only as counts
  IF(n_days >= 3, account, '_light_') AS account,
  window_start,
  COUNT(*) AS accounts,
  SUM(n_tx) AS n_tx,
  n_days,
  SUM(n_slots) AS n_slots,
  IF(n_days >= 3, ANY_VALUE(hour_mask), NULL) AS hour_mask,
  IF(n_days >= 3, ANY_VALUE(n_hours), NULL) AS n_hours,
  IF(n_days >= 3, ANY_VALUE(gap), NULL) AS gap,
  IF(n_days >= 3, ANY_VALUE(mid), NULL) AS mid,
  IF(n_days >= 3, ANY_VALUE(class), 'light') AS class
FROM classified
GROUP BY 1, 2, n_days
