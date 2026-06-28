"""Append-only audit log for kelpmesh Studio Pro."""

from __future__ import annotations
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import Column, String, Integer, DateTime, Text
from kelpmesh_studio.db import Base


class AuditEvent(Base):
    __tablename__ = "audit_log"
    id          = Column(Integer, primary_key=True)
    org_id      = Column(String, nullable=False, default="default")
    user_email  = Column(String, nullable=False)
    action      = Column(String, nullable=False)   # e.g. "run_models", "edit_model"
    resource    = Column(String, nullable=True)    # e.g. "project:my_proj/model:orders"
    ip_address  = Column(String, nullable=True)
    user_agent  = Column(String, nullable=True)
    detail      = Column(Text, nullable=True)      # JSON or free text
    created_at  = Column(DateTime, server_default=sa.func.now())


class AuditLogger:
    def __init__(self, session):
        self._session = session

    def log(
        self,
        user_email: str,
        action: str,
        resource: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        detail: Optional[str] = None,
        org_id: str = "default",
    ) -> AuditEvent:
        event = AuditEvent(
            org_id=org_id,
            user_email=user_email,
            action=action,
            resource=resource,
            ip_address=ip_address,
            user_agent=user_agent,
            detail=detail,
        )
        self._session.add(event)
        self._session.commit()
        return event

    def query(
        self,
        org_id: str = "default",
        user_email: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEvent]:
        q = self._session.query(AuditEvent).filter_by(org_id=org_id)
        if user_email:
            q = q.filter(AuditEvent.user_email == user_email)
        if action:
            q = q.filter(AuditEvent.action == action)
        return (
            q.order_by(AuditEvent.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def count(self, org_id: str = "default") -> int:
        return self._session.query(AuditEvent).filter_by(org_id=org_id).count()


def create_tables(engine) -> None:
    Base.metadata.create_all(engine)
