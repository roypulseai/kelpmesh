import os
from pathlib import Path
from pydantic import BaseModel, Field, model_validator
from typing import Optional
import yaml


_REQUIRED_FIELDS = {
    "postgres": ["host", "port", "user", "password", "database"],
    "redshift": ["host", "user", "password", "database"],
    "snowflake": ["account", "user", "password"],
    "bigquery": ["project_id"],
    "databricks": ["account", "path", "password"],
    "fabric": ["account", "database"],
    "duckdb": [],
}


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
    name: str = "briq_project"
    models_path: str = "models"
    tests_path: str = "tests"
    seeds_path: str = "seeds"
    analyses_path: str = "analyses"
    macros_path: str = "macros"
    target_path: str = "target"
    warehouse: WarehouseConfig = Field(default_factory=WarehouseConfig)
    model_directories: list[str] = Field(default_factory=lambda: ["models", "briq_packages"])
    # Project-level variables; overridden by --var at CLI
    vars: dict = Field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "ProjectConfig":
        config_file = path / "briq.yml"
        if config_file.exists():
            with open(config_file) as f:
                data = yaml.safe_load(f)
            return cls(**data)
        return cls()

    def save(self, path: Path) -> None:
        with open(path / "briq.yml", "w") as f:
            yaml.dump(self.model_dump(exclude_none=True), f, default_flow_style=False)
