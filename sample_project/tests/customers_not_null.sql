SELECT COUNT(*) AS failures
FROM customers
WHERE customer_id IS NULL
