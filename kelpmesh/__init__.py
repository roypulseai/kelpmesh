"""
kelpmesh - Code-native data transformation platform (SQL & Python models).
Zero telemetry. Zero analytics. Zero phone-home.
"""

__all__ = [
    "ProjectConfig", "Project", "KelpMeshModel",
    "SQLParser", "PythonRefParser", "MacroLoader", "DAGBuilder",
    "Executor", "StateEngine", "SchemaYaml", "DataClassifier",
    "DuckDBAdapter", "WarehouseAdapter", "ComparisonEngine",
    "PythonModelRunner", "FixtureTestRunner", "get_adapter",
    "CryptoEngine", "SubstitutionEngine", "KelpMeshError",
]

__version__ = "1.0.0"
__version_tuple__ = (1, 0, 0)
__phone_home__ = False

from kelpmesh.core.config import ProjectConfig
from kelpmesh.core.project import Project
from kelpmesh.core.model import KelpMeshModel
from kelpmesh.parser.sql import SQLParser
from kelpmesh.parser.python import PythonRefParser
from kelpmesh.core.macros import MacroLoader
from kelpmesh.core.graph import DAGBuilder
from kelpmesh.core.executor import Executor
from kelpmesh.state.engine import StateEngine
from kelpmesh.core.schema_yaml import SchemaYaml
from kelpmesh.security.classifier import DataClassifier
from kelpmesh.adapters.duckdb import DuckDBAdapter
from kelpmesh.adapters.base import WarehouseAdapter
from kelpmesh.adapters import get_adapter
from kelpmesh.diff.comparison import ComparisonEngine
from kelpmesh.core.python_runner import PythonModelRunner
from kelpmesh.testing.fixtures import FixtureTestRunner
from kelpmesh.core.crypto import CryptoEngine
from kelpmesh.core.substitutions import SubstitutionEngine
from kelpmesh.core.errors import KelpMeshError
