-- Test: example_model should have data
SELECT COUNT(*) AS failures
FROM example_model
WHERE id IS NULL
