"""Tests for seed type inference and directory scanning (seeds v2)."""

from __future__ import annotations

import csv
import io
import os
import pytest
from pathlib import Path

from briq.cli.seed import _infer_type, _csv_to_create_table_sql, _load_schema_overrides


class TestInferType:
    def test_boolean_true_false(self):
        assert _infer_type(["true", "false", "true"]) == "BOOLEAN"

    def test_boolean_1_0(self):
        assert _infer_type(["1", "0", "1", "0"]) == "BOOLEAN"

    def test_boolean_yes_no(self):
        assert _infer_type(["yes", "no"]) == "BOOLEAN"

    def test_integer(self):
        assert _infer_type(["1", "2", "3", "100", "-5"]) == "BIGINT"

    def test_float(self):
        assert _infer_type(["1.5", "2.7", "3.0"]) == "DOUBLE"

    def test_float_with_commas(self):
        assert _infer_type(["1,000.50", "2,500.00"]) == "DOUBLE"

    def test_date(self):
        assert _infer_type(["2025-01-01", "2025-12-31"]) == "DATE"

    def test_timestamp(self):
        assert _infer_type(["2025-01-01 12:00:00", "2025-06-15T08:30:00"]) == "TIMESTAMP"

    def test_varchar_mixed(self):
        assert _infer_type(["hello", "world", "123"]) == "VARCHAR"

    def test_varchar_all_nulls(self):
        assert _infer_type(["", "null", "None"]) == "VARCHAR"

    def test_empty_list(self):
        assert _infer_type([]) == "VARCHAR"


class TestCsvToCreateTableSql:
    def _write_csv(self, path: Path, rows: list[list], headers: list[str]):
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)

    def test_basic_types_inferred(self, tmp_path):
        p = tmp_path / "test.csv"
        self._write_csv(p, [
            ["1", "Alice", "2025-01-01", "true"],
            ["2", "Bob", "2025-02-01", "false"],
        ], ["id", "name", "joined", "active"])
        ddl, rows, cols = _csv_to_create_table_sql(p, "users")
        assert '"id" BIGINT' in ddl
        assert '"name" VARCHAR' in ddl
        assert '"joined" DATE' in ddl
        assert '"active" BOOLEAN' in ddl
        assert len(rows) == 2
        assert cols == ["id", "name", "joined", "active"]

    def test_schema_override_applied(self, tmp_path):
        p = tmp_path / "test.csv"
        self._write_csv(p, [["1"], ["2"]], ["id"])
        ddl, _, _ = _csv_to_create_table_sql(p, "tbl", column_types={"id": "VARCHAR"})
        assert '"id" VARCHAR' in ddl

    def test_empty_csv_returns_placeholder(self, tmp_path):
        p = tmp_path / "empty.csv"
        p.write_text("", encoding="utf-8")
        ddl, rows, cols = _csv_to_create_table_sql(p, "empty_tbl")
        assert "placeholder" in ddl
        assert rows == []

    def test_tsv_delimiter(self, tmp_path):
        p = tmp_path / "test.tsv"
        p.write_text("id\tname\n1\tAlice\n", encoding="utf-8")
        ddl, rows, cols = _csv_to_create_table_sql(p, "tbl", delimiter="\t")
        assert '"id"' in ddl
        assert '"name"' in ddl

    def test_bom_stripped(self, tmp_path):
        p = tmp_path / "bom.csv"
        p.write_bytes(b"\xef\xbb\xbfid,name\n1,Alice\n")
        ddl, _, cols = _csv_to_create_table_sql(p, "bom_tbl")
        assert cols[0] == "id"  # BOM stripped


class TestLoadSchemaOverrides:
    def test_overrides_loaded(self, tmp_path):
        seeds_dir = tmp_path / "seeds"
        seeds_dir.mkdir()
        (seeds_dir / "seeds.yml").write_text(
            "seeds:\n  - name: countries\n    column_types:\n      code: VARCHAR\n      pop: BIGINT\n",
            encoding="utf-8",
        )
        overrides = _load_schema_overrides(seeds_dir)
        assert overrides["countries"]["code"] == "VARCHAR"
        assert overrides["countries"]["pop"] == "BIGINT"

    def test_no_file_returns_empty(self, tmp_path):
        seeds_dir = tmp_path / "seeds"
        seeds_dir.mkdir()
        assert _load_schema_overrides(seeds_dir) == {}

    def test_empty_yml_returns_empty(self, tmp_path):
        seeds_dir = tmp_path / "seeds"
        seeds_dir.mkdir()
        (seeds_dir / "seeds.yml").write_text("", encoding="utf-8")
        assert _load_schema_overrides(seeds_dir) == {}
