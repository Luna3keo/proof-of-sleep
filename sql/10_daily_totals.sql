-- Plain daily activity from the raw table, for the most recent stretch of data:
-- transactions, distinct signing accounts, distinct contracts called.
SELECT
  block_date,
  COUNT(*) AS transactions,
  COUNT(DISTINCT signer_account_id) AS active_accounts,
  COUNT(DISTINCT receiver_account_id) AS contracts_called
FROM `{source}.transactions`
WHERE block_date BETWEEN DATE '2026-09-01' AND DATE '2026-11-08'
GROUP BY 1
ORDER BY 1
