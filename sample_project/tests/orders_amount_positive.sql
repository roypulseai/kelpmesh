SELECT COUNT(*) AS failures
FROM orders
WHERE amount <= 0
