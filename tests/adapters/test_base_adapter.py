from pathlib import Path
import tempfile


class BaseAdapterAcceptanceTests:
    """Abstract acceptance tests that every adapter must pass.

    Subclass with the appropriate adapter setup/teardown.
    """

    adapter = None

    def setup_method(self):
        raise NotImplementedError

    def test_connect_and_disconnect(self):
        self.adapter.connect()
        self.adapter.disconnect()

    def test_execute_returns_dicts(self):
        self.adapter.connect()
        result = self.adapter.execute("SELECT 1 AS val")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["val"] == 1
        self.adapter.disconnect()

    def test_execute_multiple_rows(self):
        self.adapter.connect()
        result = self.adapter.execute(
            "SELECT x FROM (VALUES (1), (2), (3)) AS t(x) ORDER BY x"
        )
        assert len(result) == 3
        assert [r["x"] for r in result] == [1, 2, 3]
        self.adapter.disconnect()

    def test_execute_empty_result(self):
        self.adapter.connect()
        result = self.adapter.execute(
            "SELECT 1 AS val WHERE 1 = 0"
        )
        assert isinstance(result, list)
        assert len(result) == 0
        self.adapter.disconnect()

    def test_create_and_drop_view(self):
        self.adapter.connect()
        self.adapter.execute_model(
            "SELECT 1 AS id, 'test' AS name", "test_view", materialized="view"
        )
        assert self.adapter.table_exists("test_view")
        schema = self.adapter.table_schema("test_view")
        assert len(schema) >= 2
        col_names = [c["column_name"].lower() for c in schema]
        assert "id" in col_names
        assert "name" in col_names
        self.adapter.drop_table("test_view", materialized="view")
        assert not self.adapter.table_exists("test_view")
        self.adapter.disconnect()

    def test_create_and_drop_table(self):
        self.adapter.connect()
        self.adapter.execute_model(
            "SELECT 1 AS id, 'test' AS name", "test_table", materialized="table"
        )
        assert self.adapter.table_exists("test_table")
        row_count = self.adapter.fetch_row_count("test_table")
        assert row_count == 1
        self.adapter.drop_table("test_table", materialized="table")
        assert not self.adapter.table_exists("test_table")
        self.adapter.disconnect()

    def test_preview(self):
        self.adapter.connect()
        self.adapter.execute_model(
            "SELECT x FROM (VALUES (1), (2), (3), (4), (5)) AS t(x)",
            "test_preview_table", materialized="table"
        )
        preview = self.adapter.preview("SELECT * FROM test_preview_table", limit=3)
        assert len(preview) == 3
        self.adapter.drop_table("test_preview_table", materialized="table")
        self.adapter.disconnect()

    def test_incremental_append(self):
        self.adapter.connect()
        self.adapter.execute_model(
            "SELECT 1 AS id", "test_inc", materialized="incremental"
        )
        assert self.adapter.fetch_row_count("test_inc") == 1
        self.adapter.execute_model(
            "SELECT 2 AS id", "test_inc", materialized="incremental"
        )
        assert self.adapter.fetch_row_count("test_inc") == 2
        self.adapter.drop_table("test_inc", materialized="table")
        self.adapter.disconnect()

    def test_null_handling(self):
        self.adapter.connect()
        self.adapter.execute_model(
            "SELECT NULL AS val", "test_nulls", materialized="table"
        )
        result = self.adapter.execute("SELECT val FROM test_nulls")
        assert result[0]["val"] is None
        self.adapter.drop_table("test_nulls", materialized="table")
        self.adapter.disconnect()
