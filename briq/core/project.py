from pathlib import Path
from briq.core.config import ProjectConfig
from briq.core.model import BriqModel
from briq.parser.sql import SQLParser
from briq.parser.python import PythonRefParser
from briq.semantic import SourceLoader, ExposureLoader, MetricLoader, BriqSource, BriqExposure, BriqMetric


class Project:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.config = ProjectConfig.load(self.path)
        self.models: dict[str, BriqModel] = {}
        self.sources: dict[str, BriqSource] = {}
        self.exposures: dict[str, BriqExposure] = {}
        self.metrics: dict[str, BriqMetric] = {}
        self._load_models()
        self._load_semantic()

    def _load_models(self):
        parser = SQLParser()
        py_parser = PythonRefParser()
        dirs_to_scan = list(self.config.model_directories)
        pkgs_dir = self.path / "briq_packages"
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
                model = BriqModel(
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
                model = BriqModel(
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
        if pre_hooks:
            kwargs["pre_hook"] = pre_hooks
        if post_hooks:
            kwargs["post_hook"] = post_hooks
        return kwargs

    def get_model(self, name: str) -> BriqModel | None:
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
