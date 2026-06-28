"""Phase D — Package ecosystem tests."""
import json
import tempfile
from pathlib import Path
import pytest
from kelpmesh.core.project import Project
from kelpmesh.core.packages import (
    add_package, remove_package, list_packages, install_packages,
    search_packages, package_info, create_package, KNOWN_REGISTRY,
    _packages_dir, _lock_path,
)


# ── kelpmesh-utils package ──────────────────────────────────────────────

class TestBriqUtilsPackage:
    def test_utils_package_yml_exists(self):
        """Verify kelpmesh-utils package metadata."""
        pkg_yml = Path("kelpmesh_packages/kelpmesh-utils/package.yml")
        assert pkg_yml.exists()
        content = pkg_yml.read_text(encoding="utf-8")
        assert "kelpmesh-utils" in content
        assert "0.1.0" in content

    def test_utils_models_exist(self):
        """Verify kelpmesh-utils model files."""
        models_dir = Path("kelpmesh_packages/kelpmesh-utils/models")
        assert models_dir.exists()
        models = list(models_dir.glob("*.sql"))
        names = {m.stem for m in models}
        assert "generate_series" in names
        assert "date_spine" in names
        assert "surrogate_key" in names
        assert "deduplicate" in names
        assert "hash_columns" in names

    def test_utils_models_have_descriptions(self):
        """Verify each model has a -- description header."""
        for f in sorted(Path("kelpmesh_packages/kelpmesh-utils/models").glob("*.sql")):
            content = f.read_text(encoding="utf-8")
            assert any(
                line.strip().startswith("-- description:")
                for line in content.splitlines()
            ), f"{f.name} missing description"

    def test_project_loads_utils_models(self, tmp_path):
        """Verify Project loads kelpmesh-utils models from kelpmesh_packages."""
        _init_project(tmp_path)
        project = Project(tmp_path)
        names = set(project.models.keys())
        assert "generate_series" in names
        assert "date_spine" in names

    def test_utils_models_executable(self, tmp_path):
        """Verify kelpmesh-utils models can be executed."""
        from kelpmesh.adapters.duckdb import DuckDBAdapter
        from kelpmesh.core.config import WarehouseConfig
        adapter = DuckDBAdapter(WarehouseConfig(type="duckdb", path=":memory:"))
        for name in ["generate_series", "date_spine"]:
            sql = (Path("kelpmesh_packages/kelpmesh-utils/models") / f"{name}.sql").read_text(encoding="utf-8")
            result = adapter.execute(sql)
            assert result is not None
            assert len(result) > 0
        adapter.disconnect()


# ── kelpmesh-expectations package ───────────────────────────────────────

class TestBriqExpectationsPackage:
    def test_expectations_package_yml_exists(self):
        """Verify kelpmesh-expectations package metadata."""
        pkg_yml = Path("kelpmesh_packages/kelpmesh-expectations/package.yml")
        assert pkg_yml.exists()
        content = pkg_yml.read_text(encoding="utf-8")
        assert "kelpmesh-expectations" in content
        assert "0.1.0" in content

    def test_expectation_templates_exist(self):
        """Verify expectation template files."""
        exp_dir = Path("kelpmesh_packages/kelpmesh-expectations/expectations")
        assert exp_dir.exists()
        files = list(exp_dir.glob("*.sql"))
        names = {f.stem for f in files}
        assert "not_null" in names
        assert "unique" in names
        assert "accepted_values" in names
        assert "between" in names
        assert "row_count_between" in names

    def test_expectation_templates_have_placeholders(self):
        """Verify templates contain {{ model }} and {{ column }}."""
        exp_dir = Path("kelpmesh_packages/kelpmesh-expectations/expectations")
        not_null = (exp_dir / "not_null.sql").read_text(encoding="utf-8")
        assert "{{ model }}" in not_null
        assert "{{ column }}" in not_null

    def test_expectation_templates_have_severity(self):
        """Verify templates declare severity."""
        for f in sorted(Path("kelpmesh_packages/kelpmesh-expectations/expectations").glob("*.sql")):
            content = f.read_text(encoding="utf-8")
            assert any("-- severity:" in line for line in content.splitlines()), f"{f.name} missing severity"


# ── Package registry ────────────────────────────────────────────────

class TestPackageRegistry:
    def test_search_packages_returns_all(self):
        results = search_packages()
        names = {r["name"] for r in results}
        assert "kelpmesh-utils" in names
        assert "kelpmesh-expectations" in names

    def test_search_packages_filters(self):
        results = search_packages("expect")
        assert all("expect" in r["name"].lower() or "expect" in r["description"].lower() for r in results)
        assert "kelpmesh-expectations" in {r["name"] for r in results}

    def test_package_info_known(self):
        info = package_info("kelpmesh-utils")
        assert info is not None
        assert info["name"] == "kelpmesh-utils"
        assert "version" in info
        assert "description" in info

    def test_package_info_unknown(self):
        assert package_info("nonexistent") is None

    def test_known_registry_entries_have_git(self):
        for name, info in KNOWN_REGISTRY.items():
            assert "git" in info, f"{name} missing git URL"
            assert info["git"].startswith("https://")


# ── Package manager operations ──────────────────────────────────────

class TestPackageManager:
    def test_add_package(self, tmp_path):
        add_package(tmp_path, "kelpmesh-utils")
        lock = json.loads((tmp_path / "kelpmesh.lock").read_text(encoding="utf-8"))
        assert "kelpmesh-utils" in lock["packages"]

    def test_add_package_with_version(self, tmp_path):
        add_package(tmp_path, "kelpmesh-utils", version="0.2.0")
        lock = json.loads((tmp_path / "kelpmesh.lock").read_text(encoding="utf-8"))
        assert lock["packages"]["kelpmesh-utils"]["version"] == "0.2.0"

    def test_remove_package(self, tmp_path):
        add_package(tmp_path, "test-pkg")
        pkg_dir = _packages_dir(tmp_path) / "test-pkg"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        (pkg_dir / "model.sql").write_text("select 1", encoding="utf-8")
        remove_package(tmp_path, "test-pkg")
        lock = json.loads((tmp_path / "kelpmesh.lock").read_text(encoding="utf-8"))
        assert "test-pkg" not in lock["packages"]
        assert not pkg_dir.exists()

    def test_list_packages_empty(self, tmp_path):
        assert list_packages(tmp_path) == []

    def test_list_packages_after_add(self, tmp_path):
        add_package(tmp_path, "kelpmesh-utils")
        pkgs = list_packages(tmp_path)
        names = [p["name"] for p in pkgs]
        assert "kelpmesh-utils" in names

    def test_install_from_local_dir(self, tmp_path):
        src = tmp_path / "src_pkg"
        src.mkdir()
        (src / "model.sql").write_text("select 1 as id", encoding="utf-8")
        add_package(tmp_path, "local-pkg", source=str(src))
        install_packages(tmp_path)
        dest = _packages_dir(tmp_path) / "local-pkg"
        assert dest.exists()
        assert (dest / "model.sql").exists()
        assert (dest / "model.sql").read_text(encoding="utf-8") == "select 1 as id"

    def test_install_from_local_dir_clean_reinstall(self, tmp_path):
        """Verify install removes then re-creates package dir."""
        src = tmp_path / "src_pkg"
        src.mkdir()
        (src / "v1.sql").write_text("-- v1", encoding="utf-8")
        add_package(tmp_path, "pkg", source=str(src))
        install_packages(tmp_path)
        assert (_packages_dir(tmp_path) / "pkg" / "v1.sql").exists()
        (src / "v1.sql").write_text("-- v2", encoding="utf-8")
        install_packages(tmp_path)
        content = (_packages_dir(tmp_path) / "pkg" / "v1.sql").read_text(encoding="utf-8")
        assert content == "-- v2"

    def test_lockfile_format(self, tmp_path):
        add_package(tmp_path, "pkg1")
        add_package(tmp_path, "pkg2", source="git@github.com:user/repo.git", version="1.0.0")
        lock = json.loads((tmp_path / "kelpmesh.lock").read_text(encoding="utf-8"))
        assert "packages" in lock
        assert "pkg1" in lock["packages"]
        assert lock["packages"]["pkg2"]["source"] == "git@github.com:user/repo.git"
        assert lock["packages"]["pkg2"]["version"] == "1.0.0"

    def test_builtin_packages_auto_discovered(self, tmp_path):
        """Verify the built-in kelpmesh_packages/ are discovered without kelpmesh.lock."""
        _init_project(tmp_path)
        project = Project(tmp_path)
        assert "generate_series" in project.models
        assert "date_spine" in project.models


# ── Package create ──────────────────────────────────────────────────

class TestPackageCreate:
    def test_create_package_structure(self, tmp_path):
        pkg_dir = create_package(tmp_path, "my-custom-pkg")
        assert pkg_dir.exists()
        assert (pkg_dir / "package.yml").exists()
        assert (pkg_dir / "models" / "example.sql").exists()

    def test_create_package_metadata(self, tmp_path):
        pkg_dir = create_package(tmp_path, "test-pkg")
        content = (pkg_dir / "package.yml").read_text(encoding="utf-8")
        assert "name: test-pkg" in content
        assert "version: 0.1.0" in content
        assert "Apache-2.0" in content

    def test_create_package_idempotent(self, tmp_path):
        create_package(tmp_path, "pkg")
        create_package(tmp_path, "pkg")
        assert (tmp_path / "kelpmesh_packages" / "pkg" / "package.yml").exists()


# ── Expectation generation ──────────────────────────────────────────

class TestExpectationGeneration:
    def test_not_null_generation(self, tmp_path):
        project_path = _link_builtin_packages(tmp_path)
        from kelpmesh.cli.test import _generate_expectation
        from kelpmesh.core.packages import _packages_dir
        pkgs_dir = _packages_dir(project_path)
        if not (pkgs_dir / "kelpmesh-expectations").exists():
            _link_package(pkgs_dir, "kelpmesh-expectations")

        _generate_expectation(project_path, "not_null", {"model": "ref('my_model')", "column": "id"})
        test_file = project_path / "tests" / "not_null_my_model.sql"
        assert test_file.exists(), f"Expected {test_file}"
        content = test_file.read_text(encoding="utf-8")
        assert "ref('my_model')" in content
        assert "id" in content
        assert "failures" in content

    def test_unique_generation(self, tmp_path):
        project_path = _link_builtin_packages(tmp_path)
        from kelpmesh.cli.test import _generate_expectation
        pkgs_dir = _packages_dir(project_path)
        if not (pkgs_dir / "kelpmesh-expectations").exists():
            _link_package(pkgs_dir, "kelpmesh-expectations")

        _generate_expectation(project_path, "unique", {"model": "ref('users')", "column": "email"})
        test_file = project_path / "tests" / "unique_users.sql"
        assert test_file.exists(), f"Expected {test_file}"

    def test_not_found_expectation_prints_available(self, tmp_path, capsys):
        project_path = _link_builtin_packages(tmp_path)
        from kelpmesh.cli.test import _generate_expectation
        pkgs_dir = _packages_dir(project_path)
        if not (pkgs_dir / "kelpmesh-expectations").exists():
            _link_package(pkgs_dir, "kelpmesh-expectations")

        with pytest.raises(RuntimeError):
            _generate_expectation(project_path, "nonexistent", {})
        captured = capsys.readouterr()
        assert "not_null" in captured.err or "not_null" in captured.out

    def test_generated_test_has_severity(self, tmp_path):
        project_path = _link_builtin_packages(tmp_path)
        from kelpmesh.cli.test import _generate_expectation
        pkgs_dir = _packages_dir(project_path)
        if not (pkgs_dir / "kelpmesh-expectations").exists():
            _link_package(pkgs_dir, "kelpmesh-expectations")

        _generate_expectation(project_path, "not_null", {"model": "ref('x')", "column": "y"})
        content = (project_path / "tests" / "not_null_x.sql").read_text(encoding="utf-8")
        assert "-- severity:" in content

    def test_custom_arg_override(self, tmp_path):
        project_path = _link_builtin_packages(tmp_path)
        from kelpmesh.cli.test import _generate_expectation
        pkgs_dir = _packages_dir(project_path)
        if not (pkgs_dir / "kelpmesh-expectations").exists():
            _link_package(pkgs_dir, "kelpmesh-expectations")

        _generate_expectation(project_path, "between", {
            "model": "ref('orders')", "column": "amount",
            "min_value": "10", "max_value": "1000",
        })
        content = (project_path / "tests" / "between_orders.sql").read_text(encoding="utf-8")
        assert "10" in content
        assert "1000" in content
        assert "amount" in content


# ── Helpers ─────────────────────────────────────────────────────────

def _init_project(path: Path):
    models_dir = path / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    target_dir = path / "target"
    target_dir.mkdir(exist_ok=True)
    tests_dir = path / "tests"
    tests_dir.mkdir(exist_ok=True)
    (path / "kelpmesh.yml").write_text("name: test_project\n", encoding="utf-8")
    _link_builtin_packages(path)


def _link_builtin_packages(project_path: Path) -> Path:
    """Ensure built-in packages are accessible from the temp project."""
    pkgs_dir = _packages_dir(project_path)
    pkgs_dir.mkdir(parents=True, exist_ok=True)
    for pkg_name in ["kelpmesh-utils", "kelpmesh-expectations"]:
        _link_package(pkgs_dir, pkg_name)
    return project_path


def _link_package(pkgs_dir: Path, name: str):
    """Copy built-in package into temp project."""
    src = Path("kelpmesh_packages") / name
    dest = pkgs_dir / name
    if not dest.exists():
        _copytree(src, dest)


def _copytree(src: Path, dst: Path):
    import shutil
    shutil.copytree(src, dst, dirs_exist_ok=True)
