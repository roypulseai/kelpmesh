SELECT
    o.order_date,
    COUNT(DISTINCT o.order_id) AS num_orders,
    COUNT(DISTINCT o.customer_id) AS num_customers,
    SUM(o.amount) AS revenue
FROM orders o
GROUP BY 1
ORDER BY 1
