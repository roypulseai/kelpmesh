import os
import re
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, model_validator

_REQUIRED_FIELDS = {
    "postgres": ["host", "port", "user", "password", "database"],
    "redshift": ["host", "user", "password", "database"],
    "snowflake": ["account", "user", "password"],
    "bigquery": ["project_id"],
    "databricks": ["account", "path", "password"],
    "fabric": ["account", "database"],
    "duckdb": [],
    "mysql": ["host", "user", "password", "database"],
    "trino": ["host"],
}


def _interpolate_env_vars(data: Any) -> Any:
    """Recursively replace ${VAR} and $VAR references with environment variable values."""
    if isinstance(data, dict):
        return {k: _interpolate_env_vars(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_interpolate_env_vars(v) for v in data]
    if isinstance(data, str):
        return re.sub(
            r"\$\{([^}]+)\}",
            lambda m: os.environ.get(m.group(1), m.group(0)),
            data,
        )
    return data


class WarehouseConfig(BaseModel):
    type: str = "duckdb"
    database: Optional[str] = None
    warehouse_schema: Optional[str] = Field(None, alias="schema")
    host: Optional[str] = None
    port: int = 5432
    path: Optional[str] = None
    account: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    warehouse: Optional[str] = None
    project_id: Optional[str] = None
    private_key_path: Optional[str] = None
    connection_string: Optional[str] = None
    encryption_key: Optional[str] = None
    threads: int = 4

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_required(self):
        required = _REQUIRED_FIELDS.get(self.type, [])
        missing = [f for f in required if getattr(self, f, None) is None]
        if missing:
            raise ValueError(
                f"Warehouse type '{self.type}' requires: {', '.join(missing)}"
            )
        return self


class ProjectConfig(BaseModel):
    name: str = "kelpmesh_project"
    models_path: str = "models"
    tests_path: str = "tests"
    seeds_path: str = "seeds"
    analyses_path: str = "analyses"
    macros_path: str = "macros"
    target_path: str = "target"
    warehouse: WarehouseConfig = Field(default_factory=WarehouseConfig)
    # Multi-target profiles — each key is a target name (dev/staging/prod)
    targets: dict[str, Any] = Field(default_factory=dict)
    target: str = "dev"
    model_directories: list[str] = Field(default_factory=lambda: ["models", "kelpmesh_packages"])
    vars: dict = Field(default_factory=dict)

    @classmethod
    def load(cls, path: Path, target: str | None = None) -> "ProjectConfig":
        config_file = path / "kelpmesh.yml"
        if config_file.exists():
            with open(config_file) as f:
                raw = yaml.safe_load(f) or {}
            data = _interpolate_env_vars(raw)
            cfg = cls(**data)
            # Resolve active target → warehouse if targets dict is defined
            active = target or cfg.target
            if cfg.targets and active in cfg.targets:
                target_data = cfg.targets[active]
                if isinstance(target_data, dict):
                    cfg = cfg.model_copy(update={"warehouse": WarehouseConfig(**target_data)})
            return cfg
        return cls()

    def save(self, path: Path) -> None:
        with open(path / "kelpmesh.yml", "w") as f:
            yaml.dump(self.model_dump(exclude_none=True), f, default_flow_style=False)
