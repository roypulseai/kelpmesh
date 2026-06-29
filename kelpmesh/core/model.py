from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class KelpMeshModel(BaseModel):
    name: str
    file_path: Path
    sql: Optional[str] = None
    python_code: Optional[str] = None
    language: str = "sql"
    materialized: str = "view"
    description: Optional[str] = None
    upstream: set[str] = set()
    downstream: set[str] = set()
    columns: list[dict] = []
    tags: list[str] = []
    hash: Optional[str] = None
    schema_name: Optional[str] = None
    table_name: Optional[str] = None
    alias: Optional[str] = None
    unique_key: Optional[str] = None
    incremental_strategy: str = "append"
    # Snapshot fields
    snapshot_strategy: str = "timestamp"
    snapshot_updated_at: str = "updated_at"
    # Contract enforcement
    contract_enforced: bool = False
    contract_columns: list[dict] = []
    # Hooks — SQL executed before / after materialization
    pre_hook: list[str] = []
    post_hook: list[str] = []
    # Whether this model is active (enabled: false skips it entirely)
    enabled: bool = True
    # grain: list of columns that must be unique together (post-run check)
    grain: list[str] = []
    # audits: named SQL audit queries to run after materialization (must return 0 rows)
    audits: list[str] = []
    # Incremental by time range
    time_column: Optional[str] = None
    time_grain: str = "day"          # day | hour | week | month
    # Model versioning
    version: Optional[int] = None
    latest_version: Optional[int] = None
    defined_in: Optional[str] = None  # canonical name (for versioned models)

    @property
    def ref_name(self) -> str:
        return self.name

    @property
    def relation_name(self) -> str:
        if self.alias:
            return self.alias
        return self.name
