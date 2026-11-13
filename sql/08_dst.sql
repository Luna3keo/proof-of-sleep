-- Natural experiment: when clocks change, do accounts move with them?
-- 1. Take accounts that pass the sleep test in the 14 days before a clock change.
-- 2. Sort them into regions using only where their quiet stretch sat BEFORE the change.
-- 3. Count when those same accounts were active before and after the change.
-- Placebo events use ordinary dates with no clock change anywhere.
-- Output is counts per event, group, period and hour: never individual accounts.
WITH slots AS (
  SELECT signer_account_id AS account, block_date, EXTRACT(HOUR FROM block_timestamp_utc) AS hour
  FROM `{source}.transactions`
  WHERE {dst_filter}
  GROUP BY 1, 2, 3
),
tagged AS (
  SELECT e.event, IF(s.block_date <= e.pre_end, 'pre', 'post') AS period, s.account, s.block_date, s.hour
  FROM slots AS s
  JOIN UNNEST({dst_sql}) AS e
    ON s.block_date BETWEEN e.pre_start AND e.pre_end
    OR s.block_date BETWEEN e.post_start AND e.post_end
),
days AS (
  SELECT event, period, account, block_date,
         COUNT(*) AS n_slots,
         BIT_OR(1 << hour) AS day_mask,
         ARRAY_AGG(hour) AS hours
  FROM tagged
  GROUP BY 1, 2, 3, 4
),
periods AS (
  SELECT event, period, account,
         COUNT(*) AS n_days,
         SUM(n_slots) AS n_slots,
         BIT_OR(day_mask) AS hour_mask,
         ARRAY_CONCAT_AGG(hours) AS hours
  FROM days
  GROUP BY 1, 2, 3
),
with_hours AS (
  SELECT *, ARRAY(SELECT h FROM UNNEST(GENERATE_ARRAY(0, 23)) AS h WHERE (hour_mask >> h) & 1 = 1) AS hs
  FROM periods
),
features AS (
  SELECT event, period, account, n_days, n_slots, hours, ARRAY_LENGTH(hs) AS n_hours,
    (SELECT AS STRUCT gap, start_h
     FROM (
       SELECT h AS start_h,
              COALESCE((SELECT MIN(h2) FROM UNNEST(hs) AS h2 WHERE h2 > h), hs[OFFSET(0)] + 24) - h - 1 AS gap
       FROM UNNEST(hs) AS h
     )
     ORDER BY gap DESC, start_h
     LIMIT 1) AS g
  FROM with_hours
),
pivoted AS (                                  -- both periods side by side for each account
  SELECT event, account,
    MAX(IF(period = 'pre', n_days, NULL)) AS n_days,
    MAX(IF(period = 'post', n_days, NULL)) AS post_days,
    MAX(IF(period = 'pre', n_slots, NULL)) AS n_slots,
    MAX(IF(period = 'pre', n_hours, NULL)) AS n_hours,
    MAX(IF(period = 'pre', g.gap, NULL)) AS gap,
    MAX(IF(period = 'pre', (g.start_h + 1 + g.gap / 2) - 24 * FLOOR((g.start_h + 1 + g.gap / 2) / 24), NULL)) AS pre_mid,
    ARRAY_CONCAT_AGG(IF(period = 'pre', hours, CAST([] AS ARRAY<INT64>))) AS pre_hours,
    ARRAY_CONCAT_AGG(IF(period = 'post', hours, CAST([] AS ARRAY<INT64>))) AS post_hours
  FROM features
  GROUP BY 1, 2
),
cohort AS (
  SELECT event, pre_hours, post_hours,
    CASE
      WHEN ({class_case}) = 'machine' THEN 'machines'
      WHEN ({class_case}) != 'sleeper' THEN 'drop'
      WHEN pre_mid >= 23 OR pre_mid < 3.5 THEN 'europe'
      WHEN pre_mid >= 6.5 AND pre_mid < 13 THEN 'americas'
      WHEN pre_mid >= 16 AND pre_mid < 23 THEN 'asia'
      ELSE 'in_between'
    END AS grp
  FROM pivoted
  WHERE n_days IS NOT NULL AND post_days >= 3     -- same accounts, active on both sides of the change
)
SELECT event, grp, x.period, x.hour, COUNT(*) AS slots
FROM cohort,
  UNNEST(ARRAY_CONCAT(
    ARRAY(SELECT AS STRUCT 'pre' AS period, h AS hour FROM UNNEST(pre_hours) AS h),
    ARRAY(SELECT AS STRUCT 'post' AS period, h AS hour FROM UNNEST(post_hours) AS h)
  )) AS x
WHERE grp != 'drop'
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2, 3, 4
