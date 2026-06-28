"""BI tool exporters for briq semantic layer."""

from briq.semantic.exporters.base import BaseExporter, ExportResult
from briq.semantic.exporters.manifest import ManifestExporter
from briq.semantic.exporters.looker import LookerExporter
from briq.semantic.exporters.tableau import TableauExporter
from briq.semantic.exporters.powerbi import PowerBIExporter
from briq.semantic.exporters.qlik import QlikExporter

__all__ = [
    "BaseExporter",
    "ExportResult",
    "ManifestExporter",
    "LookerExporter",
    "TableauExporter",
    "PowerBIExporter",
    "QlikExporter",
]

EXPORTERS: dict[str, type[BaseExporter]] = {
    "manifest": ManifestExporter,
    "looker": LookerExporter,
    "tableau": TableauExporter,
    "powerbi": PowerBIExporter,
    "qlik": QlikExporter,
}
