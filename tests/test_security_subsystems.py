"""Tests for security subsystems: audit, classifier, masking, RLS, erasure."""

import json
from pathlib import Path

import pytest

from kelpmesh.security.audit import AuditLog
from kelpmesh.security.classifier import DataClassifier, DEFAULT_RULES
from kelpmesh.security.masking import (
    column_mask_sql,
    get_masked_select,
    can_access_column,
    ROLE_HIERARCHY,
    ROLE_ACCESS,
)
from kelpmesh.security.rls import RlsEngine, RlsPolicy


class TestAuditLog:
    def test_record_and_query(self, tmp_path: Path):
        audit = AuditLog(tmp_path)
        e = audit.record("test.action", "alice", "table:users", status="success")
        assert e["action"] == "test.action"
        assert e["actor"] == "alice"
        results = audit.query()
        assert len(results) == 1
        assert results[0]["action"] == "test.action"

    def test_record_with_before_after(self, tmp_path: Path):
        audit = AuditLog(tmp_path)
        audit.record("update", "admin", "table:orders", before={"status": "pending"}, after={"status": "shipped"})
        results = audit.query()
        assert results[0]["before"] == {"status": "pending"}
        assert results[0]["after"] == {"status": "shipped"}

    def test_filter_by_actor(self, tmp_path: Path):
        audit = AuditLog(tmp_path)
        audit.record("a1", "alice", "r1")
        audit.record("a2", "bob", "r2")
        audit.record("a3", "alice", "r3")
        assert len(audit.query(actor="alice")) == 2
        assert len(audit.query(actor="bob")) == 1
        assert len(audit.query(actor="charlie")) == 0

    def test_filter_by_action(self, tmp_path: Path):
        audit = AuditLog(tmp_path)
        audit.record("run", "alice", "r1")
        audit.record("test", "bob", "r2")
        assert len(audit.query(action="run")) == 1

    def test_count_by_action(self, tmp_path: Path):
        audit = AuditLog(tmp_path)
        audit.record("run", "a", "r1")
        audit.record("run", "a", "r2")
        audit.record("test", "b", "r3")
        counts = audit.count_by_action()
        assert counts["run"] == 2
        assert counts["test"] == 1

    def test_clear(self, tmp_path: Path):
        audit = AuditLog(tmp_path)
        audit.record("x", "a", "r")
        audit.clear()
        assert len(audit.query()) == 0

    def test_limit(self, tmp_path: Path):
        audit = AuditLog(tmp_path)
        for i in range(10):
            audit.record(f"action_{i}", "a", f"r{i}")
        results = audit.query(limit=3)
        assert len(results) == 3


class TestDataClassifier:
    def test_builtin_classification(self):
        c = DataClassifier(Path("."))
        assert c.classify("any_table", "email") == "pii"
        assert c.classify("any_table", "credit_card") == "sensitive"
        assert c.classify("any_table", "password") == "restricted"
        assert c.classify("any_table", "id") == "internal"
        assert c.classify("any_table", "created_at") == "internal"

    def test_classify_columns(self):
        c = DataClassifier(Path("."))
        results = c.classify_columns("users", ["email", "name", "salary"])
        assert ("email", "pii") in results
        assert ("salary", "sensitive") in results
        assert ("name", "internal") in results

    def test_columns_by_sensitivity(self):
        c = DataClassifier(Path("."))
        pii_cols = c.columns_by_sensitivity("t", "pii")
        assert "email" in pii_cols
        assert "phone" in pii_cols
        assert "password" not in pii_cols

    def test_custom_rules_from_file(self, tmp_path: Path):
        rules_file = tmp_path / "classify.yml"
        rules_file.write_text("users:\n  email: internal\n  role: restricted\n", encoding="utf-8")
        c = DataClassifier(tmp_path)
        assert c.classify("users", "email") == "internal"  # override
        assert c.classify("users", "role") == "restricted"
        assert c.classify("users", "password") == "restricted"  # built-in

    def test_is_classified(self):
        c = DataClassifier(Path("."))
        assert c.is_classified("t", "email")
        assert not c.is_classified("t", "description")

    def test_generate_stub(self, tmp_path: Path):
        path = tmp_path / "classify.yml"
        DataClassifier.generate_stub(path)
        assert path.exists()
        assert "classify.yml" in path.read_text()


class TestColumnMasking:
    def test_column_mask_sql_pii_email(self):
        sql = column_mask_sql("email", "pii")
        assert sql is not None
        assert '"email"' in sql

    def test_column_mask_sql_pii_phone(self):
        sql = column_mask_sql("phone", "pii")
        assert sql is not None
        assert '"phone"' in sql

    def test_column_mask_sql_sensitive_credit_card(self):
        sql = column_mask_sql("credit_card", "sensitive")
        assert "'****-****-****-'" in sql

    def test_column_mask_sql_restricted(self):
        sql = column_mask_sql("password_hash", "restricted")
        assert sql == "'[REDACTED - RESTRICTED]'"

    def test_column_mask_sql_internal(self):
        sql = column_mask_sql("description", "internal")
        assert sql is None

    def test_can_access_column(self):
        assert can_access_column("internal", "viewer")
        assert can_access_column("restricted", "viewer") is False
        assert can_access_column("pii", "viewer") is False
        assert can_access_column("pii", "editor") is False
        assert can_access_column("pii", "admin") is True
        assert can_access_column("sensitive", "editor") is False  # editor: internal+restricted only
        assert can_access_column("sensitive", "admin") is True
        assert can_access_column("restricted", "editor") is True

    def test_get_masked_select_viewer(self, tmp_path: Path):
        classifier = DataClassifier(tmp_path)
        sql = get_masked_select("users", ["id", "email", "name"], "viewer", classifier)
        assert '"id"' in sql
        assert '"name"' in sql
        # email should be masked for viewer
        assert 'regexp_replace("email"' in sql or '"email"' not in sql.split(", ")[1]

    def test_get_masked_select_admin(self, tmp_path: Path):
        classifier = DataClassifier(tmp_path)
        sql = get_masked_select("users", ["id", "email"], "admin", classifier)
        assert '"id"' in sql
        assert '"email"' in sql  # admin sees unmasked


class TestRlsEngine:
    def test_no_policies(self):
        rls = RlsEngine(Path("."))
        assert rls.list_policies() == []

    def test_load_from_briq_yml(self, tmp_path: Path):
        kelpmesh = tmp_path / "kelpmesh.yml"
        kelpmesh.write_text("rls:\n  orders:\n    viewer: \"region = 'EU'\"\n", encoding="utf-8")
        # Change to tmp_path so it reads this kelpmesh.yml
        old_cwd = Path.cwd()
        import os
        os.chdir(tmp_path)
        try:
            rls = RlsEngine(tmp_path)
            policies = rls.list_policies()
            assert len(policies) == 1
            assert policies[0]["table"] == "orders"
            assert policies[0]["role"] == "viewer"
            assert policies[0]["filter"] == "region = 'EU'"
        finally:
            os.chdir(old_cwd)

    def test_get_filter(self):
        # Create a temporary kelpmesh.yml with RLS
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        kelpmesh = tmp / "kelpmesh.yml"
        kelpmesh.write_text("rls:\n  orders:\n    viewer: \"1=0\"\n    admin: \"1=1\"\n", encoding="utf-8")
        rls = RlsEngine(tmp)
        assert rls.get_filter("orders", "viewer") == "1=0"
        assert rls.get_filter("orders", "admin") == "1=1"
        assert rls.get_filter("orders", "editor") is None
        assert rls.get_filter("nonexistent", "viewer") is None

    def test_apply_filter(self):
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        kelpmesh = tmp / "kelpmesh.yml"
        kelpmesh.write_text("rls:\n  orders:\n    viewer: \"amount > 0\"\n", encoding="utf-8")
        rls = RlsEngine(tmp)
        sql = "SELECT * FROM orders"
        wrapped = rls.apply_filter(sql, "orders", "viewer")
        assert "amount > 0" in wrapped
        assert "SELECT * FROM" in wrapped

    def test_apply_filter_no_policy(self):
        rls = RlsEngine(Path("."))
        sql = "SELECT * FROM orders"
        assert rls.apply_filter(sql, "orders", "viewer") == sql

    def test_generate_stub(self, tmp_path: Path):
        RlsEngine.generate_stub(tmp_path / "security.yml")
        assert (tmp_path / "security.yml").exists()


class TestRolesAndAccess:
    def test_role_hierarchy(self):
        assert ROLE_HIERARCHY == ["viewer", "editor", "admin"]

    def test_role_access_pii(self):
        assert "pii" in ROLE_ACCESS["admin"]
        assert "pii" not in ROLE_ACCESS["viewer"]
        assert "pii" not in ROLE_ACCESS["editor"]

    def test_role_access_sensitive(self):
        assert "sensitive" in ROLE_ACCESS["admin"]
        assert "sensitive" not in ROLE_ACCESS["editor"]  # editor: internal+restricted only
        assert "sensitive" not in ROLE_ACCESS["viewer"]

    def test_role_access_restricted(self):
        assert "restricted" in ROLE_ACCESS["admin"]
        assert "restricted" in ROLE_ACCESS["editor"]
        assert "restricted" not in ROLE_ACCESS["viewer"]
