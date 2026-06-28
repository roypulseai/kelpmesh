SELECT
    c.customer_id,
    c.name,
    c.total_orders,
    c.total_revenue,
    c.total_revenue / NULLIF(c.total_orders, 0) AS avg_order_value,
    d.revenue AS daily_revenue
FROM customers c
LEFT JOIN daily_revenue d ON 1 = 1
