"""Role-based access control for briq Studio Pro."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import Column, String, Integer, DateTime, Boolean
from briq_studio.db import Base

# Role hierarchy: higher index = more permissions
ROLES = ["viewer", "editor", "admin", "owner"]
ROLE_RANK = {r: i for i, r in enumerate(ROLES)}


@dataclass
class Permission:
    name: str
    min_role: str   # minimum role required


PERMISSIONS = [
    Permission("view_projects",   "viewer"),
    Permission("run_models",      "editor"),
    Permission("edit_models",     "editor"),
    Permission("manage_schedules","editor"),
    Permission("manage_users",    "admin"),
    Permission("manage_api_keys", "admin"),
    Permission("view_audit_log",  "admin"),
    Permission("manage_pricing",  "owner"),
    Permission("delete_project",  "owner"),
]

PERMISSION_MAP = {p.name: p for p in PERMISSIONS}


class OrgMember(Base):
    __tablename__ = "org_members"
    id         = Column(Integer, primary_key=True)
    org_id     = Column(String, nullable=False, default="default")
    user_email = Column(String, nullable=False)
    role       = Column(String, nullable=False, default="viewer")
    invited_by = Column(String, nullable=True)
    active     = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=sa.func.now())

    __table_args__ = (
        sa.UniqueConstraint("org_id", "user_email"),
    )


class RBACManager:
    def __init__(self, session):
        self._session = session

    def get_role(self, org_id: str, user_email: str) -> Optional[str]:
        member = (
            self._session.query(OrgMember)
            .filter_by(org_id=org_id, user_email=user_email, active=True)
            .first()
        )
        return member.role if member else None

    def has_permission(self, org_id: str, user_email: str, permission: str) -> bool:
        perm = PERMISSION_MAP.get(permission)
        if not perm:
            return False
        role = self.get_role(org_id, user_email)
        if not role:
            return False
        return ROLE_RANK.get(role, -1) >= ROLE_RANK.get(perm.min_role, 99)

    def add_member(
        self,
        org_id: str,
        user_email: str,
        role: str,
        invited_by: Optional[str] = None,
    ) -> OrgMember:
        if role not in ROLES:
            raise ValueError(f"Invalid role '{role}'. Choose from: {ROLES}")
        existing = (
            self._session.query(OrgMember)
            .filter_by(org_id=org_id, user_email=user_email)
            .first()
        )
        if existing:
            existing.role = role
            existing.active = True
        else:
            existing = OrgMember(
                org_id=org_id,
                user_email=user_email,
                role=role,
                invited_by=invited_by,
            )
            self._session.add(existing)
        self._session.commit()
        return existing

    def update_role(self, org_id: str, user_email: str, new_role: str) -> bool:
        if new_role not in ROLES:
            raise ValueError(f"Invalid role '{new_role}'")
        member = (
            self._session.query(OrgMember)
            .filter_by(org_id=org_id, user_email=user_email, active=True)
            .first()
        )
        if not member:
            return False
        member.role = new_role
        self._session.commit()
        return True

    def remove_member(self, org_id: str, user_email: str) -> bool:
        member = (
            self._session.query(OrgMember)
            .filter_by(org_id=org_id, user_email=user_email, active=True)
            .first()
        )
        if not member:
            return False
        member.active = False
        self._session.commit()
        return True

    def list_members(self, org_id: str) -> list[OrgMember]:
        return (
            self._session.query(OrgMember)
            .filter_by(org_id=org_id, active=True)
            .all()
        )

    def member_count(self, org_id: str) -> int:
        return (
            self._session.query(OrgMember)
            .filter_by(org_id=org_id, active=True)
            .count()
        )


def create_tables(engine) -> None:
    Base.metadata.create_all(engine)
