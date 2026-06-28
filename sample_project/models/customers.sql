SELECT
    c.customer_id,
    c.name,
    c.email,
    c.signup_date,
    COUNT(o.order_id) AS total_orders,
    COALESCE(SUM(o.amount), 0) AS total_revenue
FROM raw_customers c
LEFT JOIN raw_orders o ON c.customer_id = o.customer_id
GROUP BY 1, 2, 3, 4
