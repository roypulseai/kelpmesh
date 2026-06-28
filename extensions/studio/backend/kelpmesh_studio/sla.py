"""SLA monitoring — expected run times and breach detection for kelpmesh Studio Pro."""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Float
from kelpmesh_studio.db import Base


class SLAConfig(Base):
    __tablename__ = "sla_configs"
    id                  = Column(Integer, primary_key=True)
    org_id              = Column(String, nullable=False, default="default")
    project_name        = Column(String, nullable=False)
    model_name          = Column(String, nullable=False)  # "*" = whole project
    expected_seconds    = Column(Float, nullable=False)
    alert_on_breach     = Column(Boolean, default=True)
    alert_channel_id    = Column(Integer, nullable=True)
    created_at          = Column(DateTime, server_default=sa.func.now())

    __table_args__ = (
        sa.UniqueConstraint("org_id", "project_name", "model_name"),
    )


class SLAManager:
    def __init__(self, session):
        self._session = session

    # ------------------------------------------------------------------ #
    # Configuration                                                        #
    # ------------------------------------------------------------------ #

    def set_sla(
        self,
        org_id: str,
        project_name: str,
        model_name: str,
        expected_seconds: float,
        alert_on_breach: bool = True,
        alert_channel_id: Optional[int] = None,
    ) -> SLAConfig:
        existing = (
            self._session.query(SLAConfig)
            .filter_by(org_id=org_id, project_name=project_name, model_name=model_name)
            .first()
        )
        if existing:
            existing.expected_seconds = expected_seconds
            existing.alert_on_breach = alert_on_breach
            existing.alert_channel_id = alert_channel_id
        else:
            existing = SLAConfig(
                org_id=org_id,
                project_name=project_name,
                model_name=model_name,
                expected_seconds=expected_seconds,
                alert_on_breach=alert_on_breach,
                alert_channel_id=alert_channel_id,
            )
            self._session.add(existing)
        self._session.commit()
        return existing

    def remove_sla(self, org_id: str, project_name: str, model_name: str) -> bool:
        cfg = (
            self._session.query(SLAConfig)
            .filter_by(org_id=org_id, project_name=project_name, model_name=model_name)
            .first()
        )
        if not cfg:
            return False
        self._session.delete(cfg)
        self._session.commit()
        return True

    def list_slas(self, org_id: str, project_name: Optional[str] = None) -> list[SLAConfig]:
        q = self._session.query(SLAConfig).filter_by(org_id=org_id)
        if project_name:
            q = q.filter_by(project_name=project_name)
        return q.all()

    def get_sla(self, org_id: str, project_name: str, model_name: str) -> Optional[SLAConfig]:
        return (
            self._session.query(SLAConfig)
            .filter_by(org_id=org_id, project_name=project_name, model_name=model_name)
            .first()
        )

    # ------------------------------------------------------------------ #
    # Breach detection                                                     #
    # ------------------------------------------------------------------ #

    def check(
        self,
        org_id: str,
        project_name: str,
        model_name: str,
        actual_seconds: float,
    ) -> dict:
        """Check whether actual_seconds breaches the configured SLA."""
        cfg = self.get_sla(org_id, project_name, model_name)
        if not cfg:
            # Fall back to project-level wildcard
            cfg = self.get_sla(org_id, project_name, "*")
        if not cfg:
            return {"breach": False, "sla_configured": False}

        breached = actual_seconds > cfg.expected_seconds
        overage = actual_seconds - cfg.expected_seconds if breached else 0.0
        return {
            "breach": breached,
            "sla_configured": True,
            "model": model_name,
            "project": project_name,
            "expected_seconds": cfg.expected_seconds,
            "actual_seconds": actual_seconds,
            "overage_seconds": round(overage, 2),
            "alert_on_breach": cfg.alert_on_breach,
            "alert_channel_id": cfg.alert_channel_id,
        }

    def report(self, org_id: str, project_name: str, run_durations: dict[str, float]) -> list[dict]:
        """Batch check. run_durations: {model_name: elapsed_seconds}."""
        results = []
        for model_name, elapsed in run_durations.items():
            result = self.check(org_id, project_name, model_name, elapsed)
            if result.get("sla_configured"):
                results.append(result)
        return results


def create_tables(engine) -> None:
    Base.metadata.create_all(engine)
