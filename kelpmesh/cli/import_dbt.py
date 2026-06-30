import csv
import re
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.console import Console
from rich.table import Table

console = Console()

_YAML_TEST_COUNT = 0


# ── dbt-macro → kelpmesh-native translation map ──────────────────────────────
# Applied after _convert_refs strips {{ ref()/source()/config() }} wrappers.
# Each rule is (regex, replacement). Rules are applied top-to-bottom; order matters
# for nested macros. Quotes inside macro args are stripped to produce native SQL.

def _strip_quotes(val: str) -> str:
    val = val.strip()
    if len(val) >= 2 and val[0] in "'\"" and val[-1] == val[0]:
        return val[1:-1]
    return val


def _split_args(arg_str: str) -> list[str]:
    """Split a macro argument list on commas (best-effort, no list parsing)."""
    parts: list[str] = []
    depth = 0
    cur = []
    for ch in arg_str:
        if ch in "([{":
            depth += 1
            cur.append(ch)
        elif ch in ")]}":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        parts.append("".join(cur).strip())
    return parts


def _convert_dbt_macros(sql: str) -> str:
    """Translate common dbt/dbt_utils/dbt_date Jinja macros to kelpmesh-native SQL.

    Best-effort regex-based translation. Untranslated `{{ }}` blocks are left in
    place so the user can find them via ``kelpmesh plan`` errors and fix manually.
    The translation map below covers the macros reported broken in field testing
    on the dbt-labs/jaffle-shop project (cents_to_dollars, dbt.date_trunc,
    dbt_utils.generate_surrogate_key, dbt_date.get_base_dates).
    """
    # {{ cents_to_dollars('col') }}  ->  (col / 100)::numeric(16, 2)
    sql = re.sub(
        r"\{\{\s*cents_to_dollars\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}",
        lambda m: f"({_strip_quotes(m.group(1))} / 100)::numeric(16, 2)",
        sql,
    )

    # {{ dbt.date_trunc('part', 'col') }}  ->  DATE_TRUNC('part', col)
    sql = re.sub(
        r"\{\{\s*dbt\.date_trunc\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*([^)]+)\s*\)\s*\}\}",
        lambda m: f"DATE_TRUNC('{m.group(1)}', {_strip_quotes(m.group(2))})",
        sql,
    )

    # {{ dbt_date.get_base_dates(...) }}  -- metricflow helper; comment out (not portable)
    sql = re.sub(
        r"\{\{\s*dbt_date\.get_base_dates\s*\([^)]*\)\s*\}\}",
        "/* TODO: replace dbt_date.get_base_dates with a kelpmesh date spine */",
        sql,
    )

    # {{ dbt_utils.generate_surrogate_key(['a', 'b']) }}  ->  generate_surrogate_key(a, b)
    # Also handles variadic form: generate_surrogate_key('a', 'b')
    def _surrogate(m: re.Match) -> str:
        raw = m.group(1).strip()
        if raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1]
        else:
            inner = raw
        cols = [_strip_quotes(p) for p in _split_args(inner)]
        return "generate_surrogate_key(" + ", ".join(cols) + ")"

    sql = re.sub(
        r"\{\{\s*dbt_utils\.generate_surrogate_key\s*\(\s*(\[[^\]]*\]|[^)]+)\s*\)\s*\}\}",
        _surrogate,
        sql,
    )

    # {{ dbt_utils.safe_divide(numerator, denominator) }}  ->  safe_divide(numerator, denominator)
    sql = re.sub(
        r"\{\{\s*dbt_utils\.safe_divide\s*\(\s*([^)]+)\s*\)\s*\}\}",
        lambda m: "safe_divide(" + ", ".join(_strip_quotes(p) for p in _split_args(m.group(1))) + ")",
        sql,
    )

    # {{ is_incremental() }}  ->  TRUE  (kelpmesh materialization header handles incremental semantics)
    sql = re.sub(r"\{\{\s*is_incremental\s*\(\s*\)\s*\}\}", "TRUE", sql)

    # {{ var('name') }} -> stripped (value unknown without project config; leave empty)
    # {{ var('name', 'default') }} -> 'default'
    sql = re.sub(
        r"\{\{\s*var\s*\(\s*['\"][^'\"]+['\"]\s*,\s*([^)]+)\s*\)\s*\}\}",
        lambda m: _strip_quotes(m.group(1)),
        sql,
    )

    return sql


# ── dbt_project.yml folder-level materialization parsing ─────────────────────

def _parse_dbt_folder_materializations(dbt_config: dict) -> dict[str, str]:
    """Walk ``models:`` section of dbt_project.yml and return ``{folder_subpath: materialized}``.

    dbt projects declare per-folder configs like::

        models:
          my_project:
            marts:
              +materialized: table
            staging:
              +materialized: view

    We collapse this to ``{"marts": "table", "staging": "view"}`` keyed by folder
    subpath relative to ``models/``. The first segment under the project name is
    used as the folder key (deeper nesting is rare in practice).
    """
    folder_mats: dict[str, str] = {}

    def _walk(node: object, prefix: str = "") -> None:
        if not isinstance(node, dict):
            return
        for key, val in node.items():
            if not isinstance(key, str):
                continue
            if key.startswith("+"):
                # +materialized, +schema, +tags, etc. — we only care about +materialized
                if key == "+materialized" and isinstance(val, str):
                    folder_mats[prefix] = val
                continue
            # key is a folder name — recurse with extended prefix
            sub = f"{prefix}/{key}" if prefix else key
            _walk(val, sub)

    models_section = dbt_config.get("models", {})
    if isinstance(models_section, dict):
        # Skip the top-level project-name key, walk its children.
        for proj_name, proj_node in models_section.items():
            _walk(proj_node, "")

    return folder_mats


def _folder_materialization_for(rel_path: Path, folder_mats: dict[str, str]) -> str | None:
    """Look up the materialization for a model located at *rel_path* (relative to models/).

    Matches the longest folder prefix in *folder_mats*. Returns None if no rule applies.
    """
    if not folder_mats:
        return None
    parts = rel_path.parts
    best_match: str | None = None
    best_len = -1
    for folder, mat in folder_mats.items():
        folder_parts = tuple(folder.split("/"))
        if len(parts) >= len(folder_parts) and parts[: len(folder_parts)] == folder_parts:
            if len(folder_parts) > best_len:
                best_len = len(folder_parts)
                best_match = mat
    return best_match


# ── dbt helpers ──────────────────────────────────────────────────────────────

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
            else:
                return None
    return None


def _import_dbt(project_dir: Path, output_dir: Path) -> None:
    dbt_path = project_dir.resolve()
    output_path = output_dir.resolve()

    if not (dbt_path / "dbt_project.yml").exists():
        console.print("[red]No dbt_project.yml found. Is this a dbt project?[/red]")
        raise typer.Exit(1)

    with open(dbt_path / "dbt_project.yml") as f:
        dbt_config = yaml.safe_load(f)

    model_paths = dbt_config.get("model-paths", ["models"])
    test_paths = dbt_config.get("test-paths", ["tests"])
    seed_paths = dbt_config.get("seed-paths", ["seeds"])
    snapshot_paths = dbt_config.get("snapshot-paths", ["snapshots"])
    analysis_paths = dbt_config.get("analysis-paths", ["analyses"])
    project_name = dbt_config.get("name", "kelpmesh_project")

    # Parse dbt_project.yml per-folder +materialized configs (e.g. marts: table)
    folder_materializations = _parse_dbt_folder_materializations(dbt_config)
    if folder_materializations:
        console.print(f"  [dim]Detected folder materializations: {folder_materializations}[/dim]")

    # Preserve original CSV seed files alongside the .sql conversions so users
    # can load them via `kelpmesh seed` (the .sql VALUES form is wrapped in
    # CREATE TABLE AS by the seed loader, but the CSV is still the canonical source).
    preserve_csv_seeds = True

    output_path.mkdir(parents=True, exist_ok=True)
    models_dir = output_path / "models"
    tests_dir = output_path / "tests"
    models_dir.mkdir(exist_ok=True)
    tests_dir.mkdir(exist_ok=True)

    stats: dict = {"models": 0, "tests": 0, "errors": 0}

    console.print("Importing dbt project...")

    for mp in model_paths:
        src_models = dbt_path / mp
        if not src_models.exists():
            continue
        for sql_file in sorted(src_models.rglob("*.sql")):
            try:
                sql = sql_file.read_text(encoding="utf-8")
                clean_sql = _convert_refs(sql)
                # Expand dbt/dbt_utils/dbt_date Jinja macros to native SQL.
                clean_sql = _convert_dbt_macros(clean_sql)
                # Materialization: prefer inline {{ config(materialized=...) }};
                # fall back to dbt_project.yml folder-level +materialized.
                materialization = _extract_materialization(sql)
                if materialization == "view":
                    folder_mat = _folder_materialization_for(
                        sql_file.relative_to(src_models), folder_materializations
                    )
                    if folder_mat:
                        materialization = folder_mat

                rel_path = sql_file.relative_to(src_models)
                dest = models_dir / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)

                header = f"-- Imported from dbt: {sql_file.relative_to(dbt_path)}\n"
                if materialization != "view":
                    header += f"-- {{ materialized: {materialization} }}\n"
                # Surface any leftover (untranslated) {{ }} so the user knows to fix.
                leftover_jinja = re.findall(r"\{\{[^}]*\}\}", clean_sql)
                if leftover_jinja:
                    header += (
                        f"-- TODO: {len(leftover_jinja)} untranslated Jinja macro(s) remain — "
                        "run `kelpmesh plan` to see parse errors, then replace manually.\n"
                    )
                dest.write_text(header + clean_sql, encoding="utf-8")
                stats["models"] += 1
            except Exception as e:
                console.print(f"  [red]Error processing {sql_file}: {e}[/red]")
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
                dest = tests_dir / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(clean_sql, encoding="utf-8")
                stats["tests"] += 1
            except Exception as e:
                console.print(f"  [red]Error processing test {test_file}: {e}[/red]")
                stats["errors"] += 1

    for sp in seed_paths:
        src_seeds = dbt_path / sp
        if not src_seeds.exists():
            continue
        for csv_file in sorted(src_seeds.rglob("*.csv")):
            try:
                table_name = csv_file.stem
                dest_dir = output_path / "seeds"
                dest_dir.mkdir(exist_ok=True)
                # Preserve the original CSV — `kelpmesh seed` loads CSVs natively via
                # read_csv_auto, which is faster and more robust than VALUES blocks.
                if preserve_csv_seeds:
                    csv_dest = dest_dir / csv_file.name
                    csv_dest.write_bytes(csv_file.read_bytes())
                # Also write a .sql wrapper (CREATE TABLE AS SELECT FROM VALUES) for
                # warehouses that don't support read_csv_auto. The seed loader will
                # auto-wrap bare SELECTs in CREATE OR REPLACE TABLE.
                dest = dest_dir / f"{table_name}.sql"
                with open(csv_file, encoding="utf-8", newline="") as f:
                    reader = csv.reader(f)
                    rows = list(reader)
                if not rows:
                    continue
                headers = rows[0]
                values = []
                for row in rows[1:]:
                    vals = ", ".join(f"'{v.replace(chr(39), chr(39)+chr(39))}'" for v in row)
                    values.append(f"({vals})")
                sql = f"-- Source: {csv_file.relative_to(dbt_path)}\n"
                sql += "SELECT * FROM (VALUES\n  " + ",\n  ".join(values) + f"\n) AS _{table_name}({', '.join(headers)})\n"
                dest.write_text(sql, encoding="utf-8")
                stats["models"] += 1
                console.print(f"  [green]Seed: {csv_file.stem}[/green]")
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
                dest = models_dir / "snapshots" / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                header = (
                    f"-- Imported from dbt snapshot: {sql_file.relative_to(dbt_path)}\n"
                    "-- { materialized: table, strategy: snapshot }\n"
                )
                dest.write_text(header + clean_sql, encoding="utf-8")
                stats["models"] += 1
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
                dest = models_dir / "analyses" / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                header = (
                    f"-- Imported from dbt analysis: {sql_file.relative_to(dbt_path)}\n"
                    "-- { materialized: ephemeral }\n"
                )
                dest.write_text(header + clean_sql, encoding="utf-8")
                stats["models"] += 1
            except Exception as e:
                console.print(f"  [red]Error processing analysis {sql_file}: {e}[/red]")
                stats["errors"] += 1

    for yp in ("sources.yml", "sources.yaml"):
        for yaml_file in sorted(dbt_path.rglob(yp)):
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
                        src_model_dir = models_dir / "sources"
                        src_model_dir.mkdir(parents=True, exist_ok=True)
                        src_file = src_model_dir / f"{tbl_name}.sql"
                        cols = tbl.get("columns", [])
                        col_list = ", ".join(c.get("name", "col") for c in cols) if cols else "*"
                        sql = f"-- Source: {src_name}.{tbl_name}\n-- {{ materialized: ephemeral }}\nSELECT {col_list} FROM {tbl_name}\n"
                        src_file.write_text(sql, encoding="utf-8")
                        stats["models"] += 1
                # Also preserve the original sources.yml so kelpmesh source list works.
                dest_sources = output_path / "sources.yml"
                if not dest_sources.exists():
                    dest_sources.write_text(yaml_file.read_text(encoding="utf-8"), encoding="utf-8")
                console.print(f"  [green]Sources: {yaml_file.relative_to(dbt_path)}[/green]")
            except Exception as e:
                console.print(f"  [red]Error converting sources {yaml_file}: {e}[/red]")
                stats["errors"] += 1

    yaml_test_count = 0
    for yp in ("schema.yml", "schema.yaml"):
        for yaml_file in sorted(dbt_path.rglob(yp)):
            try:
                model_name = yaml_file.stem
                cnt = _convert_yaml_tests(yaml_file, model_name, tests_dir)
                yaml_test_count += cnt
                # Preserve the original schema.yml in models/ so SchemaYaml can read
                # descriptions, column metadata, and contracts after import.
                rel = yaml_file.relative_to(dbt_path)
                # dbt schema files often live next to models — keep that layout.
                dest_yaml = output_path / rel
                dest_yaml.parent.mkdir(parents=True, exist_ok=True)
                dest_yaml.write_text(yaml_file.read_text(encoding="utf-8"), encoding="utf-8")
                if cnt:
                    console.print(f"  [green]Tests from {yaml_file.relative_to(dbt_path)}[/green]")
            except Exception as e:
                console.print(f"  [red]Error converting YAML {yaml_file}: {e}[/red]")
                stats["errors"] += 1

    # Also preserve any *.yml/*.yaml that declares models/sources (e.g. customers.yml)
    for yaml_file in sorted(dbt_path.rglob("*.yml")) + sorted(dbt_path.rglob("*.yaml")):
        if yaml_file.name in ("schema.yml", "schema.yaml", "dbt_project.yml", "packages.yml"):
            continue
        try:
            with open(yaml_file, encoding="utf-8") as f:
                peek = yaml.safe_load(f)
            if not isinstance(peek, dict):
                continue
            if not (peek.get("models") or peek.get("sources")):
                continue
            rel = yaml_file.relative_to(dbt_path)
            dest_yaml = output_path / rel
            if not dest_yaml.exists():
                dest_yaml.parent.mkdir(parents=True, exist_ok=True)
                dest_yaml.write_text(yaml_file.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass

    stats["tests"] += yaml_test_count

    for meta_file in ("exposures.yml", "metrics.yml"):
        meta_path = dbt_path / meta_file
        if meta_path.exists():
            try:
                with open(meta_path, encoding="utf-8") as f:
                    meta = yaml.safe_load(f)
                if meta:
                    key = meta_file.replace(".yml", "")
                    count = len(meta.get(key, []))
                    if count:
                        console.print(f"  [green]Found {count} {key} (preserved for docs)[/green]")
            except Exception:
                pass

    packages_path = dbt_path / "packages.yml"
    if packages_path.exists():
        try:
            with open(packages_path, encoding="utf-8") as f:
                pkg_data = yaml.safe_load(f)
            if pkg_data and "packages" in pkg_data:
                packages = pkg_data["packages"]
                console.print(f"  [yellow]Found {len(packages)} dbt packages — replace with kelpmesh-utils or SQL macros[/yellow]")
        except Exception:
            pass

    _write_kelpmesh_yml(output_path, project_name)
    _write_migration_report(output_path, stats, folder_materializations)

    console.print("[green]dbt project imported successfully![/green]")
    console.print(f"  Models: {stats['models']}  Tests: {stats['tests']}")
    if stats["errors"]:
        console.print(f"  [red]Errors: {stats['errors']}[/red]")
    console.print(f"\nOutput: {output_path}")
    console.print("\nNext step: [cyan]kelpmesh run[/cyan]")
    console.print("See [cyan]MIGRATION_REPORT.md[/cyan] for a summary of changes and manual review items.")


# ── SQLMesh helpers ───────────────────────────────────────────────────────────

def _parse_sqlmesh_model_block(sql: str) -> tuple[dict, str]:
    """Parse the MODEL (...) block from a SQLMesh file. Returns (config, remaining_sql)."""
    config: dict = {}

    match = re.search(r"^\s*MODEL\s*\(", sql, re.MULTILINE | re.IGNORECASE)
    if not match:
        return config, sql

    # Extract balanced parentheses content
    start = match.end() - 1
    depth = 0
    end = start
    for i, ch in enumerate(sql[start:]):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                end = start + i + 1
                break

    block = sql[start + 1 : end - 1]
    remaining = sql[end:].lstrip(";").strip()

    # name  e.g. "schema.model_name" or just "model_name"
    name_m = re.search(r"\bname\s+([\w.]+)", block, re.IGNORECASE)
    if name_m:
        config["name"] = name_m.group(1).rstrip(",").split(".")[-1]

    # kind  FULL | VIEW | INCREMENTAL_BY_UNIQUE_KEY | INCREMENTAL_BY_TIME_RANGE | SCD_TYPE_2 | EMBEDDED
    kind_m = re.search(r"\bkind\s+(\w+)", block, re.IGNORECASE)
    if kind_m:
        kind = kind_m.group(1).upper()
        config["materialized"] = {
            "FULL": "table",
            "VIEW": "view",
            "INCREMENTAL_BY_TIME_RANGE": "incremental",
            "INCREMENTAL_BY_UNIQUE_KEY": "incremental",
            "SCD_TYPE_2": "table",
            "EMBEDDED": "ephemeral",
        }.get(kind, "table")

    # unique_key from INCREMENTAL_BY_UNIQUE_KEY (unique_key col)
    uk_m = re.search(r"INCREMENTAL_BY_UNIQUE_KEY\s*\(\s*unique_key\s+([\w,\s]+?)\s*\)", block, re.IGNORECASE)
    if uk_m:
        config["unique_key"] = uk_m.group(1).strip()

    # grain (also use as unique_key fallback)
    grain_m = re.search(r"\bgrain\s+([\w,\s]+?)(?=\s*(?:,\s*\w|\)))", block, re.IGNORECASE)
    if grain_m and "unique_key" not in config:
        config["unique_key"] = grain_m.group(1).strip().rstrip(",").strip()

    # cron
    cron_m = re.search(r"\bcron\s+'([^']+)'", block, re.IGNORECASE)
    if cron_m:
        config["cron"] = cron_m.group(1)

    # audits → convert to SQL assertion strings
    audit_tests: list[str] = []
    model_name = config.get("name", "model")
    for m in re.finditer(r"UNIQUE_VALUES\s*\(\s*columns\s*=\s*\(([\w,\s]+)\)", block, re.IGNORECASE):
        for col in (c.strip() for c in m.group(1).split(",") if c.strip()):
            audit_tests.append(
                f"SELECT COUNT(*) AS failures FROM "
                f"(SELECT {col} FROM {model_name} GROUP BY {col} HAVING COUNT(*) > 1) _fail"
            )
    for m in re.finditer(r"NOT_NULL\s*\(\s*columns\s*=\s*\(([\w,\s]+)\)", block, re.IGNORECASE):
        for col in (c.strip() for c in m.group(1).split(",") if c.strip()):
            audit_tests.append(f"SELECT COUNT(*) AS failures FROM {model_name} WHERE {col} IS NULL")
    if audit_tests:
        config["_audit_tests"] = audit_tests

    return config, remaining


def _convert_sqlmesh_macros(sql: str) -> str:
    """Convert SQLMesh @macros and JINJA wrappers to plain SQL."""
    # Time macros
    sql = re.sub(r"@execution_dt\b", "CURRENT_DATE", sql)
    sql = re.sub(r"@start_dt\b", "CURRENT_DATE - INTERVAL '7 days'", sql)
    sql = re.sub(r"@end_dt\b", "CURRENT_DATE", sql)
    sql = re.sub(r"@today\b", "CURRENT_DATE", sql)
    sql = re.sub(r"@yesterday\b", "CURRENT_DATE - INTERVAL '1 day'", sql)
    sql = re.sub(r"@this_model\b", "", sql)
    # Jinja wrappers (SQLMesh allows Jinja inside JINJA_QUERY_BEGIN...JINJA_QUERY_END)
    sql = re.sub(r"JINJA_QUERY_BEGIN\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"JINJA_QUERY_END\s*;?", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"JINJA_STATEMENT_BEGIN\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"JINJA_STATEMENT_END\s*;?", "", sql, flags=re.IGNORECASE)
    # dbt-compat refs that SQLMesh also supports
    sql = re.sub(r"\{\{\s*ref\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}", r"\1", sql)
    sql = re.sub(r"\{\{\s*source\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}", r"\2", sql)
    return sql.strip()


def _import_sqlmesh(project_dir: Path, output_dir: Path) -> None:
    sm_path = project_dir.resolve()
    output_path = output_dir.resolve()

    # Detect project root — SQLMesh can have models/ subdir or models at root
    src_models = sm_path / "models" if (sm_path / "models").exists() else sm_path

    output_path.mkdir(parents=True, exist_ok=True)
    models_dir = output_path / "models"
    tests_dir = output_path / "tests"
    models_dir.mkdir(exist_ok=True)
    tests_dir.mkdir(exist_ok=True)

    stats: dict = {"models": 0, "tests": 0, "errors": 0}
    console.print("Importing SQLMesh project...")

    for sql_file in sorted(src_models.rglob("*.sql")):
        try:
            raw = sql_file.read_text(encoding="utf-8")
            config, remaining = _parse_sqlmesh_model_block(raw)
            clean_sql = _convert_sqlmesh_macros(remaining)

            model_name = config.get("name", sql_file.stem)
            materialized = config.get("materialized", "view")

            header_lines = [f"-- Imported from SQLMesh: {sql_file.relative_to(sm_path)}"]
            if materialized != "view":
                header_lines.append(f"-- {{ materialized: {materialized} }}")
            if "unique_key" in config:
                header_lines.append(f"-- {{ unique_key: {config['unique_key']} }}")
            if "cron" in config:
                header_lines.append(f"-- {{ cron: {config['cron']} }}")
            header = "\n".join(header_lines) + "\n\n"

            rel = sql_file.relative_to(src_models)
            dest = models_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(header + clean_sql, encoding="utf-8")
            stats["models"] += 1
            console.print(f"  [green]Model: {model_name}[/green]")

            for i, test_sql in enumerate(config.get("_audit_tests", [])):
                test_file = tests_dir / f"{model_name}_audit_{i}.sql"
                test_file.write_text(test_sql + "\n", encoding="utf-8")
                stats["tests"] += 1

        except Exception as e:
            console.print(f"  [red]Error: {sql_file}: {e}[/red]")
            stats["errors"] += 1

    # SQLMesh audit .sql files (audits/ directory)
    src_audits = sm_path / "audits"
    if src_audits.exists():
        for audit_file in sorted(src_audits.rglob("*.sql")):
            try:
                sql = audit_file.read_text(encoding="utf-8")
                clean = _convert_sqlmesh_macros(sql)
                dest = tests_dir / audit_file.name
                dest.write_text(f"-- Imported SQLMesh audit\n{clean}\n", encoding="utf-8")
                stats["tests"] += 1
            except Exception as e:
                console.print(f"  [red]Error: {audit_file}: {e}[/red]")
                stats["errors"] += 1

    # SQLMesh unit test YAML (tests/*.yaml) — fixture format not directly portable
    src_tests = sm_path / "tests"
    if src_tests.exists():
        for yaml_file in sorted(list(src_tests.rglob("*.yaml")) + list(src_tests.rglob("*.yml"))):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    test_data = yaml.safe_load(f)
                if not isinstance(test_data, dict):
                    continue
                for test_name, test_def in test_data.items():
                    if not isinstance(test_def, dict):
                        continue
                    model = test_def.get("model", "").split(".")[-1]
                    if model:
                        # Generate a smoke test — fixture-based unit tests need kelpmesh create_test
                        smoke = (
                            f"-- Converted from SQLMesh unit test: {test_name}\n"
                            f"-- TODO: recreate as a proper fixture with `kelpmesh create_test {model}`\n"
                            f"SELECT COUNT(*) AS failures FROM {model} HAVING COUNT(*) = 0\n"
                        )
                        dest = tests_dir / f"{test_name}.sql"
                        dest.write_text(smoke, encoding="utf-8")
                        stats["tests"] += 1
                console.print(
                    f"  [yellow]Unit tests {yaml_file.name}: converted to smoke tests "
                    f"(SQLMesh YAML fixtures → kelpmesh create_test to recreate)[/yellow]"
                )
            except Exception as e:
                console.print(f"  [red]Error: {yaml_file}: {e}[/red]")
                stats["errors"] += 1

    # Project name from config.yaml or config.py
    project_name = sm_path.name
    for cfg_name in ("config.yaml", "config.yml"):
        cfg_path = sm_path / cfg_name
        if cfg_path.exists():
            try:
                with open(cfg_path) as f:
                    sm_cfg = yaml.safe_load(f)
                if isinstance(sm_cfg, dict):
                    project_name = sm_cfg.get("project", project_name)
            except Exception:
                pass

    _write_kelpmesh_yml(output_path, project_name)

    console.print("[green]SQLMesh project imported![/green]")
    console.print(f"  Models: {stats['models']}  Tests: {stats['tests']}")
    if stats["errors"]:
        console.print(f"  [red]Errors: {stats['errors']}[/red]")
    console.print(f"\nOutput: {output_path}")
    console.print(
        "\n[yellow]Note:[/yellow] SQLMesh YAML unit test fixtures (inputs/outputs) were converted to "
        "smoke tests.\nTo recreate them as proper fixture tests: [cyan]kelpmesh create_test <model>[/cyan]"
    )
    console.print("\nNext step: [cyan]kelpmesh run[/cyan]")


# ── Shared helpers ────────────────────────────────────────────────────────────

def _write_kelpmesh_yml(output_path: Path, project_name: str) -> None:
    config = {
        "name": project_name,
        "warehouse": {"type": "duckdb", "path": "./warehouse.db"},
        "model_paths": ["models"],
        "test_paths": ["tests"],
    }
    cfg_file = output_path / "kelpmesh.yml"
    if not cfg_file.exists():
        with open(cfg_file, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False)


def _write_migration_report(output_path: Path, stats: dict, folder_mats: dict[str, str]) -> None:
    """Write a MIGRATION_REPORT.md summarising what was imported and what needs manual review."""
    lines = [
        "# Migration Report",
        "",
        "## Summary",
        f"- Models imported: {stats['models']}",
        f"- Tests generated: {stats['tests']}",
        f"- Errors: {stats['errors']}",
        "",
    ]
    if folder_mats:
        lines += ["## Materialization Overrides (from dbt_project.yml)", ""]
        for folder, mat in folder_mats.items():
            lines.append(f"- `models/{folder}/` → `{mat}`")
        lines.append("")
    # Scan imported models for leftover Jinja that needs manual fixing.
    leftover: list[str] = []
    models_dir = output_path / "models"
    if models_dir.exists():
        for sql_file in sorted(models_dir.rglob("*.sql")):
            sql_text = sql_file.read_text(encoding="utf-8", errors="ignore")
            jinja = re.findall(r"\{\{[^}]*\}\}", sql_text)
            if jinja:
                leftover.append(
                    f"- `{sql_file.relative_to(output_path)}`: {len(jinja)} untranslated macro(s)"
                )
    if leftover:
        lines += [
            "## Manual Review Required — Untranslated Jinja Macros",
            "",
            "The following models still contain `{{ }}` Jinja that could not be auto-converted.",
            "Run `kelpmesh plan` to see parse errors, then replace these macros with plain SQL.",
            "",
            *leftover,
            "",
        ]
    lines += [
        "## Next Steps",
        "1. `kelpmesh debug` — sanity-check the project",
        "2. `kelpmesh plan` — verify the DAG has no circular dependencies",
        "3. `kelpmesh seed` — load seed data (CSVs are preserved in `seeds/`)",
        "4. `kelpmesh run` — execute all models",
        "5. `kelpmesh test` — run generated assertion tests",
        "",
        "## Seed Files",
        "Original `.csv` seed files are preserved in `seeds/` alongside `.sql` wrappers.",
        "`kelpmesh seed` auto-detects CSVs and loads them via `read_csv_auto`.",
        "",
    ]
    (output_path / "MIGRATION_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def _detect_source(project_dir: Path) -> str:
    """Auto-detect project type if --from is not specified."""
    if (project_dir / "dbt_project.yml").exists():
        return "dbt"
    if (project_dir / "config.py").exists() or (project_dir / "config.yaml").exists():
        return "sqlmesh"
    # Check first model file for MODEL (...) block
    models_dir = project_dir / "models"
    if models_dir.exists():
        for sql_file in models_dir.rglob("*.sql"):
            content = sql_file.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"^\s*MODEL\s*\(", content, re.MULTILINE | re.IGNORECASE):
                return "sqlmesh"
            break
    return "dbt"


# ── CLI command ───────────────────────────────────────────────────────────────

def import_cmd(
    project_dir: Path = typer.Argument(
        ..., help="Path to existing dbt or SQLMesh project", exists=True, file_okay=False
    ),
    output_dir: Path = typer.Option(
        ".", "--output", "-o", help="Output directory for the KelpMesh project"
    ),
    source: Optional[str] = typer.Option(
        None,
        "--from",
        help="Source format: dbt or sqlmesh (auto-detected if omitted)",
        metavar="FORMAT",
    ),
):
    """Import a dbt or SQLMesh project into KelpMesh format."""
    resolved = project_dir.resolve()
    fmt = source or _detect_source(resolved)

    if fmt == "sqlmesh":
        _import_sqlmesh(resolved, output_dir)
    else:
        _import_dbt(resolved, output_dir)


# ── Interactive migration wizard ─────────────────────────────────────────────

def _scan_dbt_project(dbt_path: Path) -> dict:
    """Scan a dbt project and return summary stats without importing."""
    stats: dict = {
        "models": 0,
        "seeds": 0,
        "tests_sql": 0,
        "tests_yaml": 0,
        "snapshots": 0,
        "analyses": 0,
        "sources": 0,
        "packages": 0,
        "has_jinja": 0,
    }
    import yaml as _yaml

    try:
        with open(dbt_path / "dbt_project.yml") as f:
            cfg = _yaml.safe_load(f)
        if cfg:
            stats["project_name"] = cfg.get("name", "unknown")
    except Exception:
        stats["project_name"] = "unknown"

    for mp in cfg.get("model-paths", ["models"]) if cfg else ["models"]:
        src = dbt_path / mp
        if src.exists():
            for f in src.rglob("*.sql"):
                stats["models"] += 1
                content = f.read_text(encoding="utf-8", errors="ignore")
                if "{{" in content or "{%" in content:
                    stats["has_jinja"] += 1

    for sp in (cfg.get("seed-paths", ["seeds"]) if cfg else ["seeds"]):
        src = dbt_path / sp
        if src.exists():
            stats["seeds"] += sum(1 for _ in src.rglob("*.csv"))

    for tp in (cfg.get("test-paths", ["tests"]) if cfg else ["tests"]):
        src = dbt_path / tp
        if src.exists():
            stats["tests_sql"] += sum(1 for _ in src.rglob("*.sql"))

    for yp in ("schema.yml", "schema.yaml"):
        for yf in dbt_path.rglob(yp):
            try:
                data = _yaml.safe_load(yf.read_text(encoding="utf-8")) or {}
                if isinstance(data, list):
                    for entry in data:
                        if isinstance(entry, dict):
                            for m in entry.get("models", []):
                                if isinstance(m, dict):
                                    stats["tests_yaml"] += len(m.get("columns", {})) + len(m.get("tests", []))
                elif isinstance(data, dict):
                    for m in data.get("models", []):
                        if isinstance(m, dict):
                            stats["tests_yaml"] += len(m.get("columns", {})) + len(m.get("tests", []))
            except Exception:
                pass

    for sp in (cfg.get("snapshot-paths", ["snapshots"]) if cfg else ["snapshots"]):
        src = dbt_path / sp
        if src.exists():
            stats["snapshots"] += sum(1 for _ in src.rglob("*.sql"))

    for ap in (cfg.get("analysis-paths", ["analyses"]) if cfg else ["analyses"]):
        src = dbt_path / ap
        if src.exists():
            stats["analyses"] += sum(1 for _ in src.rglob("*.sql"))

    for yp in ("sources.yml", "sources.yaml"):
        for yf in dbt_path.rglob(yp):
            try:
                data = _yaml.safe_load(yf.read_text(encoding="utf-8")) or {}
                if isinstance(data, dict):
                    for s in data.get("sources", []):
                        stats["sources"] += len(s.get("tables", []))
            except Exception:
                pass

    if (dbt_path / "packages.yml").exists():
        try:
            data = _yaml.safe_load((dbt_path / "packages.yml").read_text(encoding="utf-8"))
            if data and "packages" in data:
                stats["packages"] = len(data["packages"])
        except Exception:
            pass

    return stats


def migrate_cmd(
    project_dir: Path = typer.Argument(
        ..., help="Path to dbt project to migrate", exists=True, file_okay=False
    ),
    output_dir: Path = typer.Option(
        ".", "--output", "-o", help="Output directory for the KelpMesh project"
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip interactive prompts and use defaults"),
):
    """Interactive migration wizard — scan, report, and import a dbt project.

    Scans the dbt project, reports what was found (models, seeds, tests, packages),
    asks for confirmation, then runs the full import with macro conversion and
    seed preservation. Produces a MIGRATION_REPORT.md in the output.

    Examples:

        kelpmesh migrate ./my-dbt-project

        kelpmesh migrate ./my-dbt-project -o ./kelpmesh-project

        kelpmesh migrate ./my-dbt-project --yes  # non-interactive
    """
    dbt_path = project_dir.resolve()
    if not (dbt_path / "dbt_project.yml").exists():
        console.print(f"[red]No dbt_project.yml found at {dbt_path}[/red]")
        raise typer.Exit(1)

    # Step 1: Scan
    console.print("\n[bold]Step 1: Scanning dbt project...[/bold]\n")
    stats = _scan_dbt_project(dbt_path)

    table = Table(title=f"dbt Project Scan: {stats['project_name']}", box=None)
    table.add_column("Item", style="cyan")
    table.add_column("Count", style="bold", justify="right")
    table.add_row("Models", str(stats["models"]))
    table.add_row("  (with Jinja macros)", str(stats["has_jinja"]))
    table.add_row("Seeds (CSV)", str(stats["seeds"]))
    table.add_row("SQL tests", str(stats["tests_sql"]))
    table.add_row("YAML tests (columns+rules)", str(stats["tests_yaml"]))
    table.add_row("Snapshots", str(stats["snapshots"]))
    table.add_row("Analyses", str(stats["analyses"]))
    table.add_row("Sources", str(stats["sources"]))
    table.add_row("Packages", str(stats["packages"]))
    console.print(table)

    if stats["has_jinja"]:
        console.print(
            f"\n[yellow]⚠ {stats['has_jinja']} model(s) contain Jinja macros.[/yellow] "
            "KelpMesh will auto-convert common macros (cents_to_dollars, dbt.date_trunc, "
            "dbt_utils.generate_surrogate_key). Untranslated macros will be listed in "
            "MIGRATION_REPORT.md for manual review."
        )

    if stats["packages"]:
        console.print(
            f"\n[yellow]⚠ {stats['packages']} dbt package(s) detected.[/yellow] "
            "Common macros from dbt_utils/dbt_date are auto-converted. "
            "Custom package macros need manual porting."
        )

    # Step 2: Confirm
    if not yes:
        console.print()
        proceed = typer.confirm("Proceed with migration?", default=True)
        if not proceed:
            console.print("[yellow]Migration cancelled.[/yellow]")
            raise typer.Exit(0)

    # Step 3: Import
    console.print("\n[bold]Step 2: Importing...[/bold]\n")
    _import_dbt(dbt_path, output_dir)

    # Step 4: Report
    report_path = output_dir.resolve() / "MIGRATION_REPORT.md"
    if report_path.exists():
        console.print("\n[green]Step 3: Migration complete![/green]")
        console.print(f"  See [cyan]{report_path}[/cyan] for the full report.")
        console.print("\nNext steps:")
        console.print(f"  1. [cyan]cd {output_dir}[/cyan]")
        console.print("  2. [cyan]kelpmesh debug[/cyan]")
        console.print("  3. [cyan]kelpmesh plan[/cyan] — check for circular deps")
        console.print("  4. [cyan]kelpmesh seed[/cyan] — load seed data")
        console.print("  5. [cyan]kelpmesh run[/cyan] — execute all models")
