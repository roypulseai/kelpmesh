"""Semantic layer: sources, exposures, metrics, and freshness tracking."""

from __future__ import annotations
from pathlib import Path
from typing import Optional
from datetime import datetime

from pydantic import BaseModel

import yaml


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

class SourceFreshness(BaseModel):
    warn_after: str = "24h"
    error_after: str = "72h"
    filter: Optional[str] = None


class SourceConfig(BaseModel):
    name: str
    table: str
    description: Optional[str] = None
    database: Optional[str] = None
    schema_name: Optional[str] = None
    loader: str = "manual"
    freshness: Optional[SourceFreshness] = None
    quoting: dict[str, bool] = {}


class KelpMeshSource(BaseModel):
    name: str
    table: str
    description: Optional[str] = None
    database: Optional[str] = None
    schema_name: Optional[str] = None
    loader: str = "manual"
    freshness: Optional[SourceFreshness] = None
    loaded_at_field: str = "loaded_at"
    # populated at freshness check time
    max_loaded_at: Optional[datetime] = None
    freshness_status: str = "unchecked"  # unchecked | pass | warn | error


# ---------------------------------------------------------------------------
# Exposures
# ---------------------------------------------------------------------------

class ExposureConfig(BaseModel):
    name: str
    type: str = "dashboard"  # dashboard | notebook | analysis | ml | application
    url: Optional[str] = None
    owner: str = "unknown"
    depends_on: list[str] = []
    description: Optional[str] = None


class KelpMeshExposure(BaseModel):
    name: str
    type: str = "dashboard"
    url: Optional[str] = None
    owner: str = "unknown"
    depends_on: list[str] = []
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

class MetricFilter(BaseModel):
    field: str
    operator: str = "="
    value: str


class MetricConfig(BaseModel):
    name: str
    model: str = ""
    label: str
    # simple types: count | sum | average | min | max | count_distinct | expression
    # composite types: ratio | derived
    type: str = "count"
    sql: Optional[str] = None
    description: Optional[str] = None
    filters: list[MetricFilter] = []
    dimensions: list[str] = []
    timestamp: Optional[str] = None
    time_granularity: str = "day"
    # ratio metric: numerator_metric / denominator_metric
    numerator: Optional[str] = None
    denominator: Optional[str] = None
    # derived metric: expression referencing other metric names as {{name}}
    expression: Optional[str] = None
    # BI tool hints
    format_string: Optional[str] = None   # e.g. "#,##0.00" or "$#,##0"
    tags: list[str] = []


class KelpMeshMetric(BaseModel):
    name: str
    model: str = ""
    label: str
    type: str = "count"
    sql: Optional[str] = None
    description: Optional[str] = None
    filters: list[MetricFilter] = []
    dimensions: list[str] = []
    timestamp: Optional[str] = None
    time_granularity: str = "day"
    numerator: Optional[str] = None
    denominator: Optional[str] = None
    expression: Optional[str] = None
    format_string: Optional[str] = None
    tags: list[str] = []

    def generate_sql(self, group_by: list[str] | None = None,
                     where: str | None = None,
                     order_by: list[str] | None = None,
                     limit: int | None = None) -> str:
        model_ref = self.model
        if self.type == "count":
            expr = "COUNT(*)"
        elif self.type == "count_distinct":
            expr = f"COUNT(DISTINCT {self.sql})" if self.sql else "COUNT(*)"
        elif self.type == "sum":
            expr = f"SUM({self.sql})" if self.sql else f"SUM({self.model}.{self.name})"
        elif self.type == "average":
            expr = f"AVG({self.sql})" if self.sql else f"AVG({self.model}.{self.name})"
        elif self.type == "min":
            expr = f"MIN({self.sql})" if self.sql else f"MIN({self.model}.{self.name})"
        elif self.type == "max":
            expr = f"MAX({self.sql})" if self.sql else f"MAX({self.model}.{self.name})"
        elif self.type == "expression":
            expr = self.sql or "NULL"
        else:
            expr = "COUNT(*)"

        select_parts = [f"{expr} AS \"{self.name}\""]
        group_cols = list(group_by or [])

        for dim in self.dimensions:
            if dim not in group_cols:
                group_cols.append(dim)

        for dim in group_cols:
            if "." not in dim:
                dim_ref = f"{model_ref}.{dim}"
            else:
                dim_ref = dim
            if dim not in [c.split(".")[-1] for c in select_parts]:
                select_parts.append(f"{dim_ref} AS \"{dim.split('.')[-1]}\"")

        sql = f"SELECT {', '.join(select_parts)}\nFROM {model_ref}"

        conditions = []
        for f in self.filters:
            conditions.append(f"{f.field} {f.operator} {f.value}")
        if where:
            conditions.append(where)
        if conditions:
            sql += "\nWHERE " + " AND ".join(conditions)

        if group_cols:
            sql += "\nGROUP BY " + ", ".join(f'"{c.split(".")[-1]}"' for c in group_cols)

        if order_by:
            sql += "\nORDER BY " + ", ".join(order_by)

        if limit is not None:
            sql += f"\nLIMIT {limit}"

        return sql


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

class SourceLoader:
    @staticmethod
    def load(project_path: Path) -> list[KelpMeshSource]:
        path = project_path / "sources.yml"
        if not path.exists():
            path = project_path / "sources.yaml"
        if not path.exists():
            return []
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        sources_raw = raw.get("sources", [])
        result = []
        for s in sources_raw:
            cfg = SourceConfig(**s)
            result.append(KelpMeshSource(
                name=cfg.name,
                table=cfg.table,
                description=cfg.description,
                database=cfg.database,
                schema_name=cfg.schema_name,
                loader=cfg.loader,
                freshness=cfg.freshness,
                loaded_at_field=cfg.freshness.filter if cfg.freshness and cfg.freshness.filter else "loaded_at",
            ))
        return result


class ExposureLoader:
    @staticmethod
    def load(project_path: Path) -> list[KelpMeshExposure]:
        path = project_path / "exposures.yml"
        if not path.exists():
            path = project_path / "exposures.yaml"
        if not path.exists():
            return []
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        exposures_raw = raw.get("exposures", [])
        result = []
        for e in exposures_raw:
            cfg = ExposureConfig(**e)
            result.append(KelpMeshExposure(
                name=cfg.name,
                type=cfg.type,
                url=cfg.url,
                owner=cfg.owner,
                depends_on=cfg.depends_on,
                description=cfg.description,
            ))
        return result


class MetricLoader:
    @staticmethod
    def load(project_path: Path) -> list[KelpMeshMetric]:
        path = project_path / "metrics.yml"
        if not path.exists():
            path = project_path / "metrics.yaml"
        if not path.exists():
            return []
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        metrics_raw = raw.get("metrics", [])
        result = []
        for m in metrics_raw:
            cfg = MetricConfig(**m)
            result.append(KelpMeshMetric(
                name=cfg.name,
                model=cfg.model,
                label=cfg.label,
                type=cfg.type,
                sql=cfg.sql,
                description=cfg.description,
                filters=cfg.filters,
                dimensions=cfg.dimensions,
                timestamp=cfg.timestamp,
                time_granularity=cfg.time_granularity,
                numerator=cfg.numerator,
                denominator=cfg.denominator,
                expression=cfg.expression,
                format_string=cfg.format_string,
                tags=cfg.tags,
            ))
        return result
