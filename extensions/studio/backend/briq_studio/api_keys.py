"""API keys / service accounts for briq Studio Pro.

Keys are hashed on storage (SHA-256). The raw value is shown exactly once
at creation time and never stored.
"""

from __future__ import annotations
import hashlib
import secrets
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text
from briq_studio.db import Base


class APIKey(Base):
    __tablename__ = "api_keys"
    id          = Column(Integer, primary_key=True)
    org_id      = Column(String, nullable=False, default="default")
    name        = Column(String, nullable=False)
    key_hash    = Column(String, unique=True, nullable=False)
    key_prefix  = Column(String, nullable=False)   # first 8 chars for display
    created_by  = Column(String, nullable=False)
    scopes      = Column(Text, default="run,read")  # comma-separated
    last_used_at = Column(DateTime, nullable=True)
    expires_at  = Column(DateTime, nullable=True)
    active      = Column(Boolean, default=True)
    created_at  = Column(DateTime, server_default=sa.func.now())


def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class APIKeyManager:
    def __init__(self, session):
        self._session = session

    def create(
        self,
        org_id: str,
        name: str,
        created_by: str,
        scopes: str = "run,read",
        expires_at: Optional[datetime] = None,
    ) -> tuple[APIKey, str]:
        """Return (APIKey record, raw_key). raw_key shown only here."""
        raw = f"bsk_{secrets.token_hex(32)}"
        record = APIKey(
            org_id=org_id,
            name=name,
            key_hash=_hash_key(raw),
            key_prefix=raw[:12],
            created_by=created_by,
            scopes=scopes,
            expires_at=expires_at,
        )
        self._session.add(record)
        self._session.commit()
        return record, raw

    def verify(self, raw_key: str, org_id: Optional[str] = None) -> Optional[APIKey]:
        """Verify a raw key and return its record (or None)."""
        h = _hash_key(raw_key)
        q = self._session.query(APIKey).filter_by(key_hash=h, active=True)
        if org_id:
            q = q.filter_by(org_id=org_id)
        record = q.first()
        if not record:
            return None
        if record.expires_at and record.expires_at < datetime.utcnow():
            return None
        record.last_used_at = datetime.utcnow()
        self._session.commit()
        return record

    def revoke(self, key_id: int, org_id: str) -> bool:
        record = (
            self._session.query(APIKey)
            .filter_by(id=key_id, org_id=org_id, active=True)
            .first()
        )
        if not record:
            return False
        record.active = False
        self._session.commit()
        return True

    def list_keys(self, org_id: str) -> list[APIKey]:
        return (
            self._session.query(APIKey)
            .filter_by(org_id=org_id, active=True)
            .order_by(APIKey.created_at.desc())
            .all()
        )

    def has_scope(self, key: APIKey, scope: str) -> bool:
        return scope in [s.strip() for s in key.scopes.split(",")]


def create_tables(engine) -> None:
    Base.metadata.create_all(engine)
