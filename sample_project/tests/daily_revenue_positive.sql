SELECT COUNT(*) AS failures
FROM daily_revenue
WHERE revenue < 0
