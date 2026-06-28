from kelpmesh.parser.sql import SQLParser


class TestSQLParser:
    def setup_method(self):
        self.parser = SQLParser()

    def test_extract_simple_select(self):
        sql = "SELECT * FROM customers"
        refs = self.parser.extract_table_references(sql)
        assert "customers" in refs

    def test_extract_joins(self):
        sql = """
        SELECT c.name, o.amount
        FROM customers c
        JOIN orders o ON c.id = o.customer_id
        """
        refs = self.parser.extract_table_references(sql)
        assert "customers" in refs
        assert "orders" in refs

    def test_extract_cte(self):
        sql = """
        WITH active AS (
            SELECT * FROM customers WHERE status = 'active'
        )
        SELECT * FROM active
        """
        refs = self.parser.extract_table_references(sql)
        assert "customers" in refs

    def test_extract_subquery(self):
        sql = """
        SELECT * FROM (
            SELECT * FROM orders WHERE amount > 100
        ) AS high_value
        """
        refs = self.parser.extract_table_references(sql)
        assert "orders" in refs

    def test_extract_multiple_tables(self):
        sql = """
        SELECT * FROM table_a
        UNION ALL
        SELECT * FROM table_b
        """
        refs = self.parser.extract_table_references(sql)
        assert "table_a" in refs
        assert "table_b" in refs

    def test_extract_columns(self):
        sql = """
        SELECT
            customer_id,
            name AS customer_name,
            COUNT(*) AS num_orders
        FROM customers
        """
        columns = self.parser.extract_columns(sql)
        names = [c["name"] for c in columns]
        assert "customer_id" in names
        assert "customer_name" in names
        assert "num_orders" in names

    def test_normalize_sql(self):
        sql = 'SELECT 1 AS "id"'
        normalized = self.parser.normalize(sql)
        assert normalized

    def test_empty_sql(self):
        refs = self.parser.extract_table_references("")
        assert refs == []

    def test_invalid_sql(self):
        refs = self.parser.extract_table_references("NOT VALID SQL {{{")
        assert refs == []
