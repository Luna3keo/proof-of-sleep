-- Who are the accounts that pass the sleep test? Sleepers by account family, with the
-- UTC hour of each sleeper's quiet stretch. A family whose sleepers all sit in the same
-- few hours looks like one program or one place, not a worldwide crowd of people.
WITH labelled AS (
  SELECT
    window_start, n_tx, class, mid,
    CASE
      WHEN REGEXP_CONTAINS(account, r'^[0-9a-f]{{64}}$') THEN 'implicit'
      WHEN REGEXP_CONTAINS(account, r'^0x[0-9a-f]{{40}}$') THEN 'eth_implicit'
      WHEN ENDS_WITH(account, '.tg') THEN 'telegram'
      WHEN ENDS_WITH(account, '.kaiching') THEN 'kaiching'
      WHEN ENDS_WITH(account, '.sweat') THEN 'sweat'
      WHEN REGEXP_CONTAINS(account, r'^[^.]+\.near$') THEN 'near_name'
      WHEN ENDS_WITH(account, '.near') THEN 'near_subaccount'
      ELSE 'other'
    END AS family
  FROM `{project}.{dataset}.account_windows`
  WHERE account != '_light_'
)
SELECT
  window_start, family, class,
  IF(class = 'sleeper', CAST(FLOOR(mid) AS INT64), -1) AS mid_hour_utc,
  COUNT(*) AS accounts,
  SUM(n_tx) AS txs
FROM labelled
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2, 3, 4
