"""Phase G — Mesh tests (cross-project refs, access control, contracts, health)."""

from __future__ import annotations
import yaml
from pathlib import Path
import pytest

from briq.mesh.config import MeshConfig, MeshProject
from briq.mesh.resolver import MeshResolver, CrossProjectRef
from briq.mesh.access import AccessPolicy, AccessChecker
from briq.mesh.contracts import (
    ProducerContract, ContractValidator, InterfaceModel, InterfaceColumn,
)
from briq.mesh.health import MeshHealthChecker, ProjectHealth


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def workspace(tmp_path) -> Path:
    """Workspace with two briq projects: core and marketing."""
    core = tmp_path / "core"
    core.mkdir()
    (core / "models").mkdir()

    (core / "models" / "dim_customers.sql").write_text(
        "SELECT id, name, segment FROM raw_customers", encoding="utf-8"
    )
    (core / "models" / "fct_orders.sql").write_text(
        "SELECT * FROM raw_orders", encoding="utf-8"
    )
    (core / "models" / "schema.yml").write_text(yaml.dump({
        "models": [
            {"name": "dim_customers", "access": "public",
             "columns": [{"name": "id"}, {"name": "segment"}]},
            {"name": "fct_orders", "access": "protected"},
        ]
    }), encoding="utf-8")
    (core / "interface.yml").write_text(yaml.dump({
        "interface": {
            "project": "core",
            "version": 1,
            "published_at": "2026-06-28",
            "models": [
                {
                    "name": "dim_customers",
                    "access": "public",
                    "version": 1,
                    "columns": [
                        {"name": "id", "data_type": "integer", "required": True},
                        {"name": "segment", "data_type": "varchar", "required": True},
                    ],
                }
            ],
        }
    }), encoding="utf-8")

    marketing = tmp_path / "marketing"
    marketing.mkdir()
    (marketing / "models").mkdir()
    (marketing / "models" / "campaign_orders.sql").write_text(
        "SELECT o.*, c.segment FROM core__fct_orders o JOIN core__dim_customers c ON o.id = c.id",
        encoding="utf-8",
    )

    (tmp_path / "mesh.yml").write_text(yaml.dump({
        "mesh": {
            "name": "acme_mesh",
            "projects": [
                {"name": "core", "path": "./core", "warehouse": "duckdb", "group": "platform"},
                {"name": "marketing", "path": "./marketing", "warehouse": "duckdb", "group": "domain"},
            ],
        }
    }), encoding="utf-8")

    return tmp_path


# ---------------------------------------------------------------------------
# MeshConfig
# ---------------------------------------------------------------------------

class TestMeshConfig:
    def test_load_mesh_yml(self, workspace):
        cfg = MeshConfig.load(workspace)
        assert cfg.name == "acme_mesh"
        assert len(cfg.projects) == 2
        assert cfg.project_names() == ["core", "marketing"]

    def test_get_project(self, workspace):
        cfg = MeshConfig.load(workspace)
        proj = cfg.get_project("core")
        assert proj is not None
        assert proj.warehouse == "duckdb"
        assert proj.group == "platform"

    def test_get_project_missing(self, workspace):
        cfg = MeshConfig.load(workspace)
        assert cfg.get_project("nonexistent") is None

    def test_empty_mesh_when_no_file(self, tmp_path):
        cfg = MeshConfig.load(tmp_path)
        assert cfg.is_empty()

    def test_project_exists(self, workspace):
        cfg = MeshConfig.load(workspace)
        proj = cfg.get_project("core")
        assert proj.exists(workspace)

    def test_write_and_reload(self, tmp_path):
        cfg = MeshConfig(
            name="test_mesh",
            projects=[MeshProject(name="p1", path=Path("./p1"), warehouse="duckdb")],
            workspace_root=tmp_path,
        )
        cfg.write(tmp_path)
        reloaded = MeshConfig.load(tmp_path)
        assert reloaded.name == "test_mesh"
        assert reloaded.project_names() == ["p1"]


# ---------------------------------------------------------------------------
# MeshResolver
# ---------------------------------------------------------------------------

class TestMeshResolver:
    def test_is_cross_ref(self):
        r = MeshResolver()
        assert r.is_cross_ref("core__dim_customers")
        assert r.is_cross_ref("marketing__fct_revenue")
        assert not r.is_cross_ref("dim_customers")
        assert not r.is_cross_ref("_private_model")
        assert not r.is_cross_ref("core_dim")   # single underscore

    def test_parse(self):
        r = MeshResolver()
        ref = r.parse("core__dim_customers")
        assert ref is not None
        assert ref.project == "core"
        assert ref.model == "dim_customers"
        assert ref.raw == "core__dim_customers"

    def test_parse_none_for_local(self):
        r = MeshResolver()
        assert r.parse("dim_customers") is None

    def test_extract_cross_refs(self):
        r = MeshResolver()
        refs = r.extract_cross_refs({"dim_customers", "core__fct_orders", "core__dim_customers"})
        names = {ref.raw for ref in refs}
        assert "core__fct_orders" in names
        assert "core__dim_customers" in names
        assert "dim_customers" not in names

    def test_rewrite_sql(self):
        r = MeshResolver()
        r.add_mapping("core__dim_customers", "dim_customers")
        r.add_mapping("core__fct_orders", "fct_orders")
        sql = "SELECT * FROM core__fct_orders o JOIN core__dim_customers c ON o.id = c.id"
        rewritten = r.rewrite_sql(sql)
        assert "core__fct_orders" not in rewritten
        assert "core__dim_customers" not in rewritten
        assert "fct_orders" in rewritten
        assert "dim_customers" in rewritten

    def test_rewrite_sql_with_env(self):
        r = MeshResolver()
        r.add_mapping("core__fct_orders", "fct_orders")
        sql = "SELECT * FROM core__fct_orders"
        rewritten = r.rewrite_sql(sql, env="dev")
        assert "dev_fct_orders" in rewritten

    def test_rewrite_sql_no_mappings_unchanged(self):
        r = MeshResolver()
        sql = "SELECT * FROM orders"
        assert r.rewrite_sql(sql) == sql

    def test_validate_refs_no_mesh(self):
        r = MeshResolver(None)
        ref = CrossProjectRef(project="core", model="dim_customers", raw="core__dim_customers")
        errors = r.validate_refs([ref], Path("."))
        assert len(errors) == 1
        assert "No mesh.yml" in errors[0]["error"]

    def test_validate_refs_unknown_project(self, workspace):
        cfg = MeshConfig.load(workspace)
        r = MeshResolver(cfg)
        ref = CrossProjectRef(project="unknown_proj", model="model", raw="unknown_proj__model")
        errors = r.validate_refs([ref], workspace)
        assert any("not in mesh.yml" in e["error"] for e in errors)

    def test_validate_refs_valid(self, workspace):
        cfg = MeshConfig.load(workspace)
        r = MeshResolver(cfg)
        ref = CrossProjectRef(project="core", model="dim_customers", raw="core__dim_customers")
        errors = r.validate_refs([ref], workspace)
        assert errors == []

    def test_build_resolution_map_from_files(self, workspace):
        cfg = MeshConfig.load(workspace)
        r = MeshResolver(cfg)
        # Should have discovered core/models/*.sql
        assert "core__dim_customers" in r._resolved
        assert "core__fct_orders" in r._resolved


# ---------------------------------------------------------------------------
# AccessChecker
# ---------------------------------------------------------------------------

class TestAccessChecker:
    def test_public_model_accessible(self, workspace):
        checker = AccessChecker(workspace / "core", project_group="platform")
        allowed, reason = checker.can_reference("dim_customers", referencing_group="domain")
        assert allowed
        assert reason == "public"

    def test_protected_model_same_group(self, workspace):
        checker = AccessChecker(workspace / "core", project_group="platform")
        allowed, reason = checker.can_reference("fct_orders", referencing_group="platform")
        assert allowed

    def test_protected_model_different_group(self, workspace):
        checker = AccessChecker(workspace / "core", project_group="platform")
        allowed, reason = checker.can_reference("fct_orders", referencing_group="domain")
        assert not allowed
        assert "protected" in reason

    def test_private_model_blocked(self, tmp_path):
        schema = tmp_path / "schema.yml"
        schema.write_text(yaml.dump({
            "models": [{"name": "secret_model", "access": "private"}]
        }), encoding="utf-8")
        checker = AccessChecker(tmp_path, project_group="platform")
        allowed, reason = checker.can_reference("secret_model", referencing_group="platform")
        assert not allowed
        assert "private" in reason

    def test_list_public_models(self, workspace):
        checker = AccessChecker(workspace / "core", project_group="platform")
        public = checker.list_public_models()
        assert "dim_customers" in public
        assert "fct_orders" not in public

    def test_default_access_when_no_schema(self, tmp_path):
        checker = AccessChecker(tmp_path, project_group="g1")
        policy = checker.get_policy("any_model", default_access="public")
        assert policy.access == "public"

    def test_access_policy_helpers(self):
        assert AccessPolicy("m", access="public").is_public()
        assert AccessPolicy("m", access="protected").is_protected()
        assert AccessPolicy("m", access="private").is_private()
        assert not AccessPolicy("m", access="public").is_private()


# ---------------------------------------------------------------------------
# ProducerContract / ContractValidator
# ---------------------------------------------------------------------------

class TestProducerContract:
    def test_load_interface_yml(self, workspace):
        contract = ProducerContract.load(workspace / "core")
        assert contract is not None
        assert contract.project == "core"
        assert len(contract.models) == 1
        m = contract.models[0]
        assert m.name == "dim_customers"
        assert m.access == "public"

    def test_load_returns_none_when_missing(self, tmp_path):
        assert ProducerContract.load(tmp_path) is None

    def test_get_model(self, workspace):
        contract = ProducerContract.load(workspace / "core")
        m = contract.get_model("dim_customers")
        assert m is not None
        assert len(m.columns) == 2

    def test_public_models_filter(self, workspace):
        contract = ProducerContract.load(workspace / "core")
        pub = contract.public_models()
        assert all(m.access == "public" for m in pub)

    def test_write_and_reload(self, tmp_path):
        contract = ProducerContract(
            project="test_project",
            version=2,
            published_at="2026-06-28",
            models=[
                InterfaceModel(
                    name="orders",
                    access="public",
                    version=1,
                    columns=[InterfaceColumn(name="id", data_type="integer")],
                )
            ],
        )
        contract.write(tmp_path)
        reloaded = ProducerContract.load(tmp_path)
        assert reloaded is not None
        assert reloaded.project == "test_project"
        assert reloaded.get_model("orders") is not None


class TestContractValidator:
    def test_valid_contract(self, workspace):
        contract = ProducerContract.load(workspace / "core")
        validator = ContractValidator()
        violations = validator.validate(contract, workspace / "core")
        assert violations == []

    def test_missing_column_violation(self, workspace):
        # Remove 'segment' column from schema.yml but keep it in interface.yml
        schema_path = workspace / "core" / "models" / "schema.yml"
        schema_path.write_text(yaml.dump({
            "models": [
                {"name": "dim_customers", "access": "public",
                 "columns": [{"name": "id"}]},  # segment removed
            ]
        }), encoding="utf-8")
        contract = ProducerContract.load(workspace / "core")
        validator = ContractValidator()
        violations = validator.validate(contract, workspace / "core")
        kinds = [v.kind for v in violations]
        assert "missing_column" in kinds

    def test_model_removed_violation(self, workspace):
        # Remove dim_customers from schema.yml entirely
        schema_path = workspace / "core" / "models" / "schema.yml"
        schema_path.write_text(yaml.dump({
            "models": [{"name": "fct_orders", "access": "protected"}]
        }), encoding="utf-8")
        contract = ProducerContract.load(workspace / "core")
        validator = ContractValidator()
        violations = validator.validate(contract, workspace / "core")
        assert any(v.kind == "model_removed" for v in violations)

    def test_access_downgrade_violation(self, workspace):
        # Downgrade dim_customers from public to protected in schema.yml
        schema_path = workspace / "core" / "models" / "schema.yml"
        schema_path.write_text(yaml.dump({
            "models": [
                {"name": "dim_customers", "access": "protected",
                 "columns": [{"name": "id"}, {"name": "segment"}]},
            ]
        }), encoding="utf-8")
        contract = ProducerContract.load(workspace / "core")
        validator = ContractValidator()
        violations = validator.validate(contract, workspace / "core")
        assert any(v.kind == "access_downgrade" for v in violations)

    def test_no_violations_when_no_contract(self, tmp_path):
        validator = ContractValidator()
        contract = ProducerContract(project="empty", models=[])
        violations = validator.validate(contract, tmp_path)
        assert violations == []


# ---------------------------------------------------------------------------
# MeshHealthChecker
# ---------------------------------------------------------------------------

class TestMeshHealthChecker:
    def test_full_check(self, workspace):
        cfg = MeshConfig.load(workspace)
        checker = MeshHealthChecker(cfg)
        report = checker.check()
        assert report.mesh_name == "acme_mesh"
        assert report.project_count == 2
        assert len(report.project_health) == 2

    def test_all_paths_exist(self, workspace):
        cfg = MeshConfig.load(workspace)
        checker = MeshHealthChecker(cfg)
        report = checker.check()
        for ph in report.project_health:
            assert ph.path_exists, f"{ph.name} path missing"

    def test_cross_refs_detected_in_marketing(self, workspace):
        cfg = MeshConfig.load(workspace)
        checker = MeshHealthChecker(cfg)
        report = checker.check()
        marketing_health = next(ph for ph in report.project_health if ph.name == "marketing")
        ref_names = {r.raw for r in marketing_health.cross_refs}
        assert "core__fct_orders" in ref_names
        assert "core__dim_customers" in ref_names

    def test_access_violation_for_protected_model(self, workspace):
        cfg = MeshConfig.load(workspace)
        checker = MeshHealthChecker(cfg)
        # marketing (domain group) references core__fct_orders which is protected in core (platform group)
        report = checker.check()
        marketing_health = next(ph for ph in report.project_health if ph.name == "marketing")
        # fct_orders is protected and groups differ → should be flagged
        violation_refs = {v["ref"] for v in marketing_health.access_violations}
        assert "core__fct_orders" in violation_refs

    def test_healthy_project_with_public_only(self, workspace):
        # Make all cross-project refs public
        schema_path = workspace / "core" / "models" / "schema.yml"
        schema_path.write_text(yaml.dump({
            "models": [
                {"name": "dim_customers", "access": "public"},
                {"name": "fct_orders", "access": "public"},
            ]
        }), encoding="utf-8")
        cfg = MeshConfig.load(workspace)
        checker = MeshHealthChecker(cfg)
        report = checker.check()
        marketing_health = next(ph for ph in report.project_health if ph.name == "marketing")
        assert marketing_health.access_violations == []

    def test_missing_project_path(self, tmp_path):
        (tmp_path / "mesh.yml").write_text(yaml.dump({
            "mesh": {
                "name": "broken_mesh",
                "projects": [
                    {"name": "ghost", "path": "./does_not_exist", "warehouse": "duckdb"},
                ],
            }
        }), encoding="utf-8")
        cfg = MeshConfig.load(tmp_path)
        checker = MeshHealthChecker(cfg)
        report = checker.check()
        assert report.project_health[0].path_exists is False
        assert report.project_health[0].status == "missing"

    def test_cross_project_graph(self, workspace):
        cfg = MeshConfig.load(workspace)
        checker = MeshHealthChecker(cfg)
        graph = checker.cross_project_graph()
        assert "marketing" in graph
        assert "core" in graph["marketing"]
        assert graph["core"] == []

    def test_check_single_project(self, workspace):
        cfg = MeshConfig.load(workspace)
        checker = MeshHealthChecker(cfg)
        ph = checker.check_project("core")
        assert ph is not None
        assert ph.name == "core"
        assert ph.path_exists

    def test_check_nonexistent_project(self, workspace):
        cfg = MeshConfig.load(workspace)
        checker = MeshHealthChecker(cfg)
        ph = checker.check_project("unknown")
        assert ph is None

    def test_core_has_interface(self, workspace):
        cfg = MeshConfig.load(workspace)
        checker = MeshHealthChecker(cfg)
        report = checker.check()
        core_health = next(ph for ph in report.project_health if ph.name == "core")
        assert core_health.has_interface

    def test_marketing_no_interface(self, workspace):
        cfg = MeshConfig.load(workspace)
        checker = MeshHealthChecker(cfg)
        report = checker.check()
        mkt_health = next(ph for ph in report.project_health if ph.name == "marketing")
        assert not mkt_health.has_interface

    def test_report_counts(self, workspace):
        # Make everything healthy: all cross refs public
        schema_path = workspace / "core" / "models" / "schema.yml"
        schema_path.write_text(yaml.dump({
            "models": [
                {"name": "dim_customers", "access": "public"},
                {"name": "fct_orders", "access": "public"},
            ]
        }), encoding="utf-8")
        cfg = MeshConfig.load(workspace)
        checker = MeshHealthChecker(cfg)
        report = checker.check()
        assert report.total_issues == 0
        assert report.all_healthy


# ---------------------------------------------------------------------------
# Mesh + briq CLI smoke test
# ---------------------------------------------------------------------------

class TestMeshCLI:
    def test_mesh_init(self, tmp_path):
        from typer.testing import CliRunner
        from briq.cli.mesh import mesh_app
        runner = CliRunner()
        result = runner.invoke(mesh_app, ["init", "--name", "test_mesh",
                                          "--workspace", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / "mesh.yml").exists()

    def test_mesh_init_already_exists(self, tmp_path):
        (tmp_path / "mesh.yml").write_text("mesh:\n  name: existing\n  projects: []\n")
        from typer.testing import CliRunner
        from briq.cli.mesh import mesh_app
        runner = CliRunner()
        result = runner.invoke(mesh_app, ["init", "--workspace", str(tmp_path)])
        assert result.exit_code == 0
        assert "already exists" in result.output

    def test_mesh_status(self, workspace):
        from typer.testing import CliRunner
        from briq.cli.mesh import mesh_app
        runner = CliRunner()
        result = runner.invoke(mesh_app, ["status", "--workspace", str(workspace)])
        assert result.exit_code == 0
        assert "acme_mesh" in result.output
        assert "core" in result.output
        assert "marketing" in result.output

    def test_mesh_validate_with_violation(self, workspace):
        from typer.testing import CliRunner
        from briq.cli.mesh import mesh_app
        runner = CliRunner()
        # fct_orders is protected → marketing (different group) accessing it = violation
        result = runner.invoke(mesh_app, ["validate", "--workspace", str(workspace)])
        # Should exit non-zero when violations exist
        assert result.exit_code != 0

    def test_mesh_graph(self, workspace):
        from typer.testing import CliRunner
        from briq.cli.mesh import mesh_app
        runner = CliRunner()
        result = runner.invoke(mesh_app, ["graph", "--workspace", str(workspace)])
        assert result.exit_code == 0
        assert "core" in result.output
        assert "marketing" in result.output

    def test_mesh_publish(self, workspace):
        from typer.testing import CliRunner
        from briq.cli.mesh import mesh_app
        runner = CliRunner()
        result = runner.invoke(mesh_app, [
            "publish",
            "--project-dir", str(workspace / "core"),
            "--name", "core",
            "--workspace", str(workspace),
        ])
        assert result.exit_code == 0
        assert "dim_customers" in result.output
