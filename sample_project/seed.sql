CREATE TABLE IF NOT EXISTS raw_customers AS
SELECT * FROM (VALUES
    (1, 'Alice', 'alice@example.com', '2024-01-15'),
    (2, 'Bob', 'bob@example.com', '2024-02-20'),
    (3, 'Charlie', 'charlie@example.com', '2024-03-10'),
    (4, 'Diana', 'diana@example.com', '2024-04-05'),
    (5, 'Eve', 'eve@example.com', '2024-05-01')
) AS t(customer_id, name, email, signup_date);

CREATE TABLE IF NOT EXISTS raw_orders AS
SELECT * FROM (VALUES
    (101, 1, 150.00, '2024-06-01'),
    (102, 1, 75.00, '2024-06-15'),
    (103, 2, 200.00, '2024-06-20'),
    (104, 3, 50.00, '2024-07-01'),
    (105, 3, 25.00, '2024-07-05'),
    (106, 1, 300.00, '2024-07-10'),
    (107, 4, 100.00, '2024-07-15'),
    (108, 5, 0.00, '2024-07-20')
) AS t(order_id, customer_id, amount, order_date);
