"""Anomaly detection — row count and null rate deviation vs rolling baseline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AnomalyAlert:
    model: str
    metric: str          # "row_count" | "null_rate"
    current: float
    baseline: float
    deviation_pct: float
    severity: str        # "warn" | "error"

    def __str__(self) -> str:
        return (
            f"[{self.severity.upper()}] {self.model} — {self.metric} "
            f"deviated {self.deviation_pct:+.0f}% "
            f"(current: {self.current:.0f}, baseline: {self.baseline:.0f})"
        )


def check_row_count_anomaly(
    model_name: str,
    current_count: int,
    history: list[int],
    warn_threshold: float = 0.30,
    error_threshold: float = 0.70,
) -> AnomalyAlert | None:
    """Return an alert if *current_count* deviates from the rolling baseline.

    Args:
        model_name: Name of the model.
        current_count: Row count from the just-completed run.
        history: Last N row counts (oldest first), not including current.
        warn_threshold: Fractional deviation that triggers a warning (0.30 = 30%).
        error_threshold: Fractional deviation that triggers an error.

    Returns:
        An :class:`AnomalyAlert` if a threshold is breached, else ``None``.
    """
    if len(history) < 3:
        return None

    baseline = sum(history) / len(history)
    if baseline == 0:
        return None

    deviation = abs(current_count - baseline) / baseline

    if deviation >= error_threshold:
        severity = "error"
    elif deviation >= warn_threshold:
        severity = "warn"
    else:
        return None

    return AnomalyAlert(
        model=model_name,
        metric="row_count",
        current=float(current_count),
        baseline=baseline,
        deviation_pct=(current_count - baseline) / baseline * 100,
        severity=severity,
    )
