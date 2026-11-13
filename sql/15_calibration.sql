-- Chance check. About 8,000 randomly chosen accounts from one 14-day window, each as a list
-- of daily activity masks (one 24-bit number per active day). No account names leave BigQuery.
-- pipeline/analyze.py shuffles each day around the clock and re-runs the test on the result.
WITH slots AS (
  SELECT signer_account_id AS account, block_date, EXTRACT(HOUR FROM block_timestamp_utc) AS hour
  FROM `{source}.transactions`
  WHERE block_date BETWEEN DATE '2026-10-01' AND DATE '2026-10-14'
  GROUP BY 1, 2, 3
),
daymask AS (
  SELECT account, block_date, BIT_OR(1 << hour) AS m
  FROM slots
  GROUP BY 1, 2
),
acct AS (
  SELECT account, ARRAY_AGG(m ORDER BY block_date) AS ms
  FROM daymask
  GROUP BY 1
  HAVING ARRAY_LENGTH(ms) >= {min_days}
)
SELECT ARRAY_TO_STRING(ARRAY(SELECT FORMAT('%x', m) FROM UNNEST(ms) AS m), ',') AS day_masks
FROM acct
WHERE MOD(ABS(FARM_FINGERPRINT(account)), 100) < 14
