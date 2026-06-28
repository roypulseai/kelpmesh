from pathlib import Path
from pydantic import BaseModel
from typing import Optional


class BriqModel(BaseModel):
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

    @property
    def ref_name(self) -> str:
        return self.name

    @property
    def relation_name(self) -> str:
        if self.alias:
            return self.alias
        return self.name
