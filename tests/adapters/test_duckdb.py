from pathlib import Path
import tempfile
from briq.adapters.duckdb import DuckDBAdapter
from briq.core.config import WarehouseConfig
from tests.adapters.test_base_adapter import BaseAdapterAcceptanceTests


class TestDuckDBAdapter(BaseAdapterAcceptanceTests):
    def setup_method(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        config = WarehouseConfig(
            type="duckdb",
            path=str(self.tmpdir / "test.duckdb"),
        )
        self.adapter = DuckDBAdapter(config, project_path=str(self.tmpdir))
        self.adapter.connect()
