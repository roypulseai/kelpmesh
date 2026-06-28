import csv
import typer
from pathlib import Path
from rich.console import Console
import yaml
import re
from kelpmesh.core.config import ProjectConfig

console = Console()

_YAML_TEST_COUNT = 0


def _convert_refs(sql: str) -> str:
    sql = re.sub(r"\{\{\s*ref\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}", r"\1", sql)
    sql = re.sub(r"\{\{\s*source\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}", r"\2", sql)
    sql = re.sub(r"\{\{?\s*config\s*\([^}]*\)\s*\}?\}", "", sql)
    sql = re.sub(r"\{\{?\s*this\s*\}?\}", "", sql)
    sql = re.sub(r"\{\{?\s*except\s*\([^)]*\)\s*\}?\}", "", sql)
    sql = re.sub(r"\{\{?\s*set\s*\([^)]*\)\s*\}?\}", "", sql)
    sql = re.sub(r"\{\{\s*var\s*\(\s*['\"]([^'\"]+)['\"]\s*(?:,\s*(.*?))?\s*\)\s*\}\}", r"\2", sql)
    sql = re.sub(r"\{\{\s*env_var\s*\(\s*['\"]([^'\"]+)['\"]\s*(?:,\s*(.*?))?\s*\)\s*\}\}", r"\2", sql)
    sql = re.sub(r"\{\{\s*target\s*\.\s*(\w+)\s*\}\}", "", sql)
    sql = re.sub(r"\{\{\s*invocation_id\s*\}\}", "", sql)
    sql = re.sub(r"\{\{%-?\s*docs\s+[^%]*%-?\}\}", "", sql)
    sql = re.sub(r"\{\{%-?\s*enddocs\s*%-?\}\}", "", sql)
    return sql.strip()


def _extract_materialization(sql: str) -> str:
    match = re.search(
        r"\{\{?\s*config\s*\([^}]*materialized\s*=\s*['\"](\w+)['\"]",
        sql,
    )
    return match.group(1) if match else "view"


def _extract_model_config(sql: str) -> dict:
    config = {}
    config["materialized"] = _extract_materialization(sql)
    match = re.search(r"\{\{?\s*config\s*\([^}]*unique_key\s*=\s*['\"](\w+)['\"]", sql)
    if match:
        config["unique_key"] = match.group(1)
    return config


def _convert_yaml_tests(yaml_path: Path, model_name: str, output_dir: Path) -> int:
    """Convert dbt schema.yml tests to SQL assertion files."""
    global _YAML_TEST_COUNT
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        return 0

    count = 0
    for version_elem in data:
        models_list = version_elem.get("models", []) if isinstance(version_elem, dict) else []
        if not models_list:
            models_list = data.get("models", []) if isinstance(data, dict) else []

    if not models_list:
        models_list = []
        if isinstance(data, dict):
            for key in ("models", "sources", "seeds", "snapshots"):
                models_list.extend(data.get(key, []))

    for entry in models_list:
        if not isinstance(entry, dict):
            continue
        entry_name = entry.get("name", model_name)
        columns = entry.get("columns", {})
        tests = entry.get("tests", [])

        test_lines = []
        for test in tests:
            sql = _convert_generic_test(test, entry_name)
            if sql:
                test_lines.append(sql)

        for col_name, col_def in columns.items():
            if isinstance(col_def, dict):
                col_tests = col_def.get("tests", [])
                for test in col_tests:
                    sql = _convert_generic_test(test, entry_name, col_name)
                    if sql:
                        test_lines.append(sql)

        if test_lines:
            test_file = output_dir / f"{entry_name}.sql"
            test_file.write_text("\n\n".join(test_lines) + "\n", encoding="utf-8")
            count += len(test_lines)
            _YAML_TEST_COUNT += 1

    return count


def _convert_generic_test(test, model_name: str, column: str | None = None) -> str | None:
    if isinstance(test, str):
        if test == "not_null" and column:
            return f"SELECT COUNT(*) AS failures FROM {model_name} WHERE {column} IS NULL"
        elif test == "unique" and column:
            return f"SELECT COUNT(*) AS failures FROM (SELECT {column} FROM {model_name} GROUP BY {column} HAVING COUNT(*) > 1) _fail"
        return None
    if isinstance(test, dict):
        for test_type, params in test.items():
            if test_type == "not_null" and column:
                return f"SELECT COUNT(*) AS failures FROM {model_name} WHERE {column} IS NULL"
            elif test_type == "unique" and column:
                return f"SELECT COUNT(*) AS failures FROM (SELECT {column} FROM {model_name} GROUP BY {column} HAVING COUNT(*) > 1) _fail"
            elif test_type == "accepted_values" and column:
                vals = params.get("values", []) if isinstance(params, dict) else params
                if isinstance(vals, list):
                    quoted = ", ".join(f"'{v}'" for v in vals)
                    return f"SELECT COUNT(*) AS failures FROM {model_name} WHERE {column} NOT IN ({quoted})"
            elif test_type == "relationships" and column:
                ref = params.get("to", "") if isinstance(params, dict) else ""
                ref_field = params.get("field", "id") if isinstance(params, dict) else "id"
                return (
                    f"SELECT COUNT(*) AS failures FROM {model_name} AS _from\n"
                    f"LEFT JOIN {ref} AS _to ON _from.{column} = _to.{ref_field}\n"
                    f"WHERE _from.{column} IS NOT NULL AND _to.{ref_field} IS NULL"
                )
            elif test_type == "dbt_utils.expression_is_true":
                expression = params.get("expression", "1=1") if isinstance(params, dict) else "1=1"
                return f"SELECT COUNT(*) AS failures FROM {model_name} WHERE NOT ({expression})"
            elif test_type == "dbt_utils.recency":
                return None
            else:
                return None
    return None


def import_cmd(
    dbt_project_dir: Path = typer.Argument(
        ..., help="Path to existing dbt project", exists=True, file_okay=False
    ),
    output_dir: Path = typer.Option(
        ".", "--output", "-o", help="Output directory for kelpmesh project"
    ),
):
    dbt_path = dbt_project_dir.resolve()
    output_path = output_dir.resolve()

    if not (dbt_path / "dbt_project.yml").exists():
        console.print("[red]No dbt_project.yml found in specified directory.[/red]")
        raise typer.Exit(1)

    with open(dbt_path / "dbt_project.yml") as f:
        dbt_config = yaml.safe_load(f)

    model_paths = dbt_config.get("model-paths", ["models"])
    test_paths = dbt_config.get("test-paths", ["tests"])
    seed_paths = dbt_config.get("seed-paths", ["seeds"])
    snapshot_paths = dbt_config.get("snapshot-paths", ["snapshots"])
    analysis_paths = dbt_config.get("analysis-paths", ["analyses"])
    project_name = dbt_config.get("name", "briq_project")

    output_path.mkdir(parents=True, exist_ok=True)
    briq_models_dir = output_path / "models"
    briq_tests_dir = output_path / "tests"
    briq_models_dir.mkdir(exist_ok=True)
    briq_tests_dir.mkdir(exist_ok=True)

    stats = {"models": 0, "tests": 0, "errors": 0}

    console.print("Importing dbt project...")

    for mp in model_paths:
        src_models = dbt_path / mp
        if not src_models.exists():
            continue
        for sql_file in sorted(src_models.rglob("*.sql")):
            try:
                sql = sql_file.read_text(encoding="utf-8")
                clean_sql = _convert_refs(sql)
                materialization = _extract_materialization(sql)

                rel_path = sql_file.relative_to(src_models)
                dest = briq_models_dir / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)

                header = f"-- Imported from dbt: {sql_file.relative_to(dbt_path)}\n"
                if materialization != "view":
                    header += f"-- {{ materialized: {materialization} }}\n"
                dest.write_text(header + clean_sql, encoding="utf-8")
                stats["models"] += 1
            except Exception as e:
                console.print(
                    f"  [red]Error processing {sql_file}: {e}[/red]"
                )
                stats["errors"] += 1

    for tp in test_paths:
        src_tests = dbt_path / tp
        if not src_tests.exists():
            continue
        for test_file in sorted(src_tests.rglob("*.sql")):
            try:
                sql = test_file.read_text(encoding="utf-8")
                clean_sql = _convert_refs(sql)
                rel_path = test_file.relative_to(src_tests)
                dest = briq_tests_dir / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(clean_sql, encoding="utf-8")
                stats["tests"] += 1
            except Exception as e:
                console.print(
                    f"  [red]Error processing test {test_file}: {e}[/red]"
                )
                stats["errors"] += 1

    for sp in seed_paths:
        src_seeds = dbt_path / sp
        if not src_seeds.exists():
            continue
        for csv_file in sorted(src_seeds.rglob("*.csv")):
            try:
                rel_path = csv_file.relative_to(src_seeds)
                table_name = csv_file.stem
                dest_dir = output_path / "seeds"
                dest_dir.mkdir(exist_ok=True)
                dest = dest_dir / f"{table_name}.sql"
                with open(csv_file, encoding="utf-8", newline="") as f:
                    reader = csv.reader(f)
                    rows = list(reader)
                if not rows:
                    continue
                headers = rows[0]
                sample = rows[1] if len(rows) > 1 else []
                col_defs = ", ".join(f'"{h}" VARCHAR' for h in headers)
                values = []
                for row in rows[1:]:
                    vals = ", ".join(f"'{v.replace(chr(39), chr(39)+chr(39))}'" for v in row)
                    values.append(f"({vals})")
                sql = f"-- Source: {csv_file.relative_to(dbt_path)}\n"
                sql += f"SELECT * FROM (VALUES\n  " + ",\n  ".join(values) + f"\n) AS _{table_name}({', '.join(headers)})\n"
                dest.write_text(sql, encoding="utf-8")
                stats["models"] = stats.get("models", 0) + 1
                console.print(f"  [green]Imported seed: {csv_file.relative_to(dbt_path)}[/green]")
            except Exception as e:
                console.print(f"  [red]Error processing seed {csv_file}: {e}[/red]")
                stats["errors"] += 1

    for sp in snapshot_paths:
        src_snapshots = dbt_path / sp
        if not src_snapshots.exists():
            continue
        for sql_file in sorted(src_snapshots.rglob("*.sql")):
            try:
                sql = sql_file.read_text(encoding="utf-8")
                clean_sql = _convert_refs(sql)
                rel_path = sql_file.relative_to(src_snapshots)
                dest = briq_models_dir / "snapshots" / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                header = f"-- Imported from dbt snapshot: {sql_file.relative_to(dbt_path)}\n-- {{ materialized: table, strategy: snapshot }}\n"
                dest.write_text(header + clean_sql, encoding="utf-8")
                stats["models"] = stats.get("models", 0) + 1
            except Exception as e:
                console.print(f"  [red]Error processing snapshot {sql_file}: {e}[/red]")
                stats["errors"] += 1

    for ap in analysis_paths:
        src_analyses = dbt_path / ap
        if not src_analyses.exists():
            continue
        for sql_file in sorted(src_analyses.rglob("*.sql")):
            try:
                sql = sql_file.read_text(encoding="utf-8")
                clean_sql = _convert_refs(sql)
                rel_path = sql_file.relative_to(src_analyses)
                dest = briq_models_dir / "analyses" / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                header = f"-- Imported from dbt analysis: {sql_file.relative_to(dbt_path)}\n-- {{ materialized: ephemeral }}\n"
                dest.write_text(header + clean_sql, encoding="utf-8")
                stats["models"] = stats.get("models", 0) + 1
            except Exception as e:
                console.print(f"  [red]Error processing analysis {sql_file}: {e}[/red]")
                stats["errors"] += 1

    for yp in ("**/sources.yml", "**/sources.yaml"):
        for yaml_file in sorted(dbt_path.rglob(yp.replace("**/", ""))):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    src_data = yaml.safe_load(f)
                if not src_data:
                    continue
                sources_list = src_data.get("sources", []) if isinstance(src_data, dict) else []
                for src in sources_list:
                    src_name = src.get("name", "source")
                    for tbl in src.get("tables", []):
                        tbl_name = tbl.get("name", "unknown")
                        src_model_dir = briq_models_dir / "sources"
                        src_model_dir.mkdir(parents=True, exist_ok=True)
                        src_file = src_model_dir / f"{tbl_name}.sql"
                        cols = tbl.get("columns", [])
                        col_list = ", ".join(c.get("name", "col") for c in cols) if cols else "*"
                        sql = f"-- Source: {src_name}.{tbl_name}\n-- {{ materialized: ephemeral }}\nSELECT {col_list} FROM {tbl_name}\n"
                        src_file.write_text(sql, encoding="utf-8")
                        stats["models"] = stats.get("models", 0) + 1
                console.print(f"  [green]Converted sources from {yaml_file.relative_to(dbt_path)}[/green]")
            except Exception as e:
                console.print(f"  [red]Error converting sources {yaml_file}: {e}[/red]")
                stats["errors"] += 1

    yaml_test_count = 0
    yaml_patterns = ["**/schema.yml", "**/schema.yaml"]
    for yp in yaml_patterns:
        for yaml_file in sorted(dbt_path.rglob(yp.replace("**/", ""))):
            try:
                model_name = yaml_file.stem
                cnt = _convert_yaml_tests(yaml_file, model_name, briq_tests_dir)
                yaml_test_count += cnt
                if cnt:
                    console.print(f"  [green]Converted YAML tests from {yaml_file.relative_to(dbt_path)}[/green]")
            except Exception as e:
                console.print(f"  [red]Error converting YAML {yaml_file}: {e}[/red]")
                stats["errors"] += 1

    if yaml_test_count:
        stats["tests"] += yaml_test_count

    exposures_path = dbt_path / "exposures.yml"
    if exposures_path.exists():
        try:
            with open(exposures_path, encoding="utf-8") as f:
                exp_data = yaml.safe_load(f)
            if exp_data and "exposures" in exp_data:
                console.print(f"  [green]Found {len(exp_data['exposures'])} exposures (noted for docs)[/green]")
                stats.setdefault("exposures", len(exp_data["exposures"]))
        except Exception as e:
            console.print(f"  [red]Error reading exposures: {e}[/red]")

    metrics_path = dbt_path / "metrics.yml"
    if metrics_path.exists():
        try:
            with open(metrics_path, encoding="utf-8") as f:
                met_data = yaml.safe_load(f)
            if met_data and "metrics" in met_data:
                console.print(f"  [green]Found {len(met_data['metrics'])} metrics (noted for docs)[/green]")
                stats.setdefault("metrics", len(met_data["metrics"]))
        except Exception as e:
            console.print(f"  [red]Error reading metrics: {e}[/red]")

    packages_path = dbt_path / "packages.yml"
    if packages_path.exists():
        try:
            with open(packages_path, encoding="utf-8") as f:
                pkg_data = yaml.safe_load(f)
            if pkg_data and "packages" in pkg_data:
                packages = pkg_data["packages"]
                console.print(f"  [yellow]Found {len(packages)} dbt packages:")
                for pkg in packages:
                    if isinstance(pkg, dict):
                        name = pkg.get("package", "?")
                        console.print(f"    - {name} (no kelpmesh equivalent yet)")
                console.print("  [yellow]Consider replacing with kelpmesh-utils or SQL macros.[/yellow]")
                stats.setdefault("packages", len(packages))
        except Exception as e:
            console.print(f"  [red]Error reading packages: {e}[/red]")

    console.print("[green]dbt project imported successfully![/green]")
    console.print(f"  Models: {stats['models']}")
    console.print(f"  Tests: {stats['tests']}")
    if stats["errors"]:
        console.print(f"  [red]Errors: {stats['errors']}[/red]")
    console.print(f"\nOutput: {output_path}")
    console.print("\nNext step: [cyan]kelpmesh run[/cyan]")
