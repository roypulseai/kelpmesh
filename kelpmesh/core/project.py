__all__ = ["Project"]

from pathlib import Path

from kelpmesh.core.config import ProjectConfig
from kelpmesh.core.macros import MacroLoader, load_builtins
from kelpmesh.core.model import KelpMeshModel
from kelpmesh.parser.python import PythonRefParser
from kelpmesh.parser.sql import SQLParser
from kelpmesh.semantic import (
    ExposureLoader,
    KelpMeshExposure,
    KelpMeshMetric,
    KelpMeshSource,
    MetricLoader,
    SourceLoader,
)


class Project:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.config = ProjectConfig.load(self.path)
        self.models: dict[str, KelpMeshModel] = {}
        self.sources: dict[str, KelpMeshSource] = {}
        self.exposures: dict[str, KelpMeshExposure] = {}
        self.metrics: dict[str, KelpMeshMetric] = {}
        self.macro_loader: MacroLoader = self._load_macros()
        self._load_models()
        self._load_semantic()

    def _load_macros(self) -> MacroLoader:
        """Load macros from macros/ directory + built-ins."""
        load_builtins()
        from kelpmesh.core.macros import get_loader
        loader = get_loader()
        macros_dir = self.path / self.config.macros_path
        loader.load_dirs([macros_dir])
        return loader

    def _load_models(self):
        parser = SQLParser()
        py_parser = PythonRefParser()
        dirs_to_scan = list(self.config.model_directories)
        pkgs_dir = self.path / "kelpmesh_packages"
        if pkgs_dir.exists():
            for sub in sorted(pkgs_dir.iterdir()):
                if sub.is_dir() and not sub.name.startswith("."):
                    dirs_to_scan.append(str(sub.relative_to(self.path)))
        # analyses/ treated as compiled-only (materialized="analysis")
        analyses_dir = self.path / self.config.analyses_path
        if analyses_dir.exists():
            dirs_to_scan.append(self.config.analyses_path)
        for model_dir in dirs_to_scan:
            dir_path = self.path / model_dir
            if not dir_path.exists():
                continue
            for sql_file in sorted(dir_path.rglob("*.sql")):
                name = sql_file.stem
                sql = sql_file.read_text(encoding="utf-8")
                refs = parser.extract_table_references(sql)
                upstream = set()
                for ref in refs:
                    if ref != name:
                        upstream.add(ref)
                source_refs = parser.extract_source_references(sql)
                upstream |= set(source_refs)
                model_kwargs = self._parse_header_config(sql, comment="--")
                # analyses/ directory → compile-only, never materialized
                if sql_file.is_relative_to(self.path / self.config.analyses_path):
                    model_kwargs.setdefault("materialized", "analysis")
                model = KelpMeshModel(
                    name=name,
                    file_path=sql_file,
                    sql=sql,
                    language="sql",
                    upstream=upstream,
                    **model_kwargs,
                )
                self.models[name] = model
            for py_file in sorted(dir_path.rglob("*.py")):
                name = py_file.stem
                source = py_file.read_text(encoding="utf-8")
                refs = py_parser.extract_refs(source)
                upstream = {r for r in refs if r != name}
                source_refs = py_parser.extract_sources(source)
                upstream |= set(source_refs)
                model_kwargs = self._parse_header_config(source, comment="#")
                if "materialized" not in model_kwargs:
                    model_kwargs["materialized"] = "table"
                model = KelpMeshModel(
                    name=name,
                    file_path=py_file,
                    python_code=source,
                    language="python",
                    upstream=upstream,
                    **model_kwargs,
                )
                self.models[name] = model

        for name, model in self.models.items():
            for up in model.upstream:
                if up in self.models:
                    self.models[up].downstream.add(name)

        # Wire up model versioning metadata
        from kelpmesh.core.versioning import register_versions
        register_versions(self.models)

    def _load_semantic(self):
        for s in SourceLoader.load(self.path):
            self.sources[s.name] = s
        for e in ExposureLoader.load(self.path):
            self.exposures[e.name] = e
        for m in MetricLoader.load(self.path):
            self.metrics[m.name] = m

    def _parse_header_config(self, source: str, comment: str = "--") -> dict:
        kwargs: dict = {}
        pre_hooks: list[str] = []
        post_hooks: list[str] = []
        for line in source.splitlines():
            stripped = line.strip()
            if not stripped.startswith(comment + " "):
                break
            header = stripped[len(comment) + 1:].strip()
            if ":" in header:
                key, val = header.split(":", 1)
                key = key.strip().lower()
                val = val.strip()
                if key == "materialized":
                    kwargs["materialized"] = val
                elif key == "unique_key":
                    kwargs["unique_key"] = val
                elif key == "incremental_strategy":
                    kwargs["incremental_strategy"] = val
                elif key == "description":
                    kwargs["description"] = val
                elif key == "alias":
                    kwargs["alias"] = val
                elif key == "schema":
                    kwargs["schema_name"] = val
                elif key == "tags":
                    kwargs["tags"] = [t.strip() for t in val.split(",")]
                elif key == "snapshot_strategy":
                    kwargs["snapshot_strategy"] = val
                elif key == "snapshot_updated_at":
                    kwargs["snapshot_updated_at"] = val
                elif key == "pre_hook":
                    pre_hooks.append(val)
                elif key == "post_hook":
                    post_hooks.append(val)
                elif key == "enabled":
                    kwargs["enabled"] = val.lower() not in ("false", "0", "no")
                elif key == "grain":
                    kwargs["grain"] = [g.strip() for g in val.split(",")]
                elif key == "audits":
                    kwargs["audits"] = [a.strip() for a in val.split(",")]
                elif key == "time_column":
                    kwargs["time_column"] = val
                elif key == "time_grain":
                    kwargs["time_grain"] = val
                elif key == "version":
                    try:
                        kwargs["version"] = int(val)
                    except ValueError:
                        pass
                elif key == "defined_in":
                    kwargs["defined_in"] = val
                elif key == "contract":
                    kwargs["contract_enforced"] = val.lower() not in ("false", "0", "no")
        if pre_hooks:
            kwargs["pre_hook"] = pre_hooks
        if post_hooks:
            kwargs["post_hook"] = post_hooks
        return kwargs

    def get_model(self, name: str) -> KelpMeshModel | None:
        return self.models.get(name)

    def get_downstream(self, name: str) -> set[str]:
        result = set()
        model = self.models.get(name)
        if model:
            for d in model.downstream:
                result.add(d)
                result |= self.get_downstream(d)
        return result

    def get_upstream(self, name: str) -> set[str]:
        result = set()
        model = self.models.get(name)
        if model:
            for u in model.upstream:
                result.add(u)
                result |= self.get_upstream(u)
        return result
