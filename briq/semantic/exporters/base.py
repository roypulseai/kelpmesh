"""Abstract base class for all BI tool exporters."""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from briq.semantic import BriqMetric, BriqSource, BriqExposure


@dataclass
class ExportResult:
    """Files written by an exporter, keyed by relative path."""
    files: dict[str, str] = field(default_factory=dict)  # path → content
    format: str = ""

    def write_to(self, output_dir: Path) -> list[Path]:
        """Materialise all files under output_dir, return paths written."""
        written: list[Path] = []
        for rel, content in self.files.items():
            dest = output_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            written.append(dest)
        return written


class BaseExporter(ABC):
    """Contract every BI exporter must satisfy."""

    format: str = ""

    def __init__(
        self,
        metrics: list["BriqMetric"],
        sources: list["BriqSource"] | None = None,
        exposures: list["BriqExposure"] | None = None,
        project_name: str = "briq_project",
    ):
        self.metrics = metrics
        self.sources = sources or []
        self.exposures = exposures or []
        self.project_name = project_name

    @abstractmethod
    def export(self) -> ExportResult:
        """Return an ExportResult containing all generated file content."""

    # ---- helpers -----------------------------------------------------------

    def _safe_name(self, name: str) -> str:
        """Snake-case, alphanumeric + underscores only."""
        import re
        return re.sub(r"[^a-z0-9_]", "_", name.lower())

    def _label(self, metric: "BriqMetric") -> str:
        return metric.label or metric.name.replace("_", " ").title()

    def _description(self, metric: "BriqMetric") -> str:
        return metric.description or f"Metric: {self._label(metric)}"
