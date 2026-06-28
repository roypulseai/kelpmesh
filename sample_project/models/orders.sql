SELECT
    order_id,
    customer_id,
    amount,
    order_date,
    CASE
        WHEN amount >= 100 THEN 'high_value'
        WHEN amount >= 50 THEN 'medium_value'
        ELSE 'low_value'
    END AS order_tier
FROM raw_orders
WHERE amount > 0
