"""Configurable pricing — tier definitions, promo codes, per-org overrides."""

from __future__ import annotations
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
import sqlalchemy as sa
from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean
from kelpmesh_studio.db import Base
from kelpmesh_studio.licensing import F_ADV_SCHEDULING, F_SSO, F_AUDIT_LOG

_PACKAGE_DEFAULT = Path(__file__).parent / "pricing.yml"


# ---------------------------------------------------------------------------
# DB models
# ---------------------------------------------------------------------------

class PromoCode(Base):
    __tablename__ = "promo_codes"
    id          = Column(Integer, primary_key=True)
    code        = Column(String, unique=True, nullable=False)
    description = Column(String, default="")
    # discount_type: "pct" (0-100) or "fixed" (CHF off)
    discount_type  = Column(String, nullable=False, default="pct")
    discount_value = Column(Float, nullable=False, default=0.0)
    # applicable_tiers: comma-sep tier names, empty = all
    applicable_tiers = Column(String, default="")
    max_uses    = Column(Integer, default=0)   # 0 = unlimited
    used_count  = Column(Integer, default=0)
    expires_at  = Column(DateTime, nullable=True)
    active      = Column(Boolean, default=True)
    created_at  = Column(DateTime, server_default=sa.func.now())


class OrgPricing(Base):
    """Per-organisation custom price override (discounts, deals, pilots)."""
    __tablename__ = "org_pricing"
    id            = Column(Integer, primary_key=True)
    org_id        = Column(String, unique=True, nullable=False)
    tier          = Column(String, nullable=False)
    # If set, overrides the tier's base price entirely
    custom_price_chf = Column(Float, nullable=True)
    # Applied promo code (for audit trail)
    promo_code    = Column(String, nullable=True)
    note          = Column(String, default="")
    valid_until   = Column(DateTime, nullable=True)
    created_at    = Column(DateTime, server_default=sa.func.now())


# ---------------------------------------------------------------------------
# Tier definition
# ---------------------------------------------------------------------------

@dataclass
class TierConfig:
    name: str
    price_monthly_chf: float
    max_users: int          # 0 = unlimited
    max_models: int
    max_projects: int
    max_schedules_per_project: int
    pro_features: bool = False
    sso: bool = False
    audit_log: bool = False
    rbac: bool = False
    api_keys: bool = False
    git_sync: bool = False
    alerts: bool = False
    support: str = "Community"

    def unlimited(self, field_name: str) -> bool:
        return getattr(self, field_name, 0) == 0

    def allows(self, feature: str) -> bool:
        return bool(getattr(self, feature, False))


# ---------------------------------------------------------------------------
# Pricing engine
# ---------------------------------------------------------------------------

class PricingEngine:
    """Load tier config from pricing.yml and resolve effective prices."""

    def __init__(self, config_path: Optional[Path] = None):
        self._path = config_path or self._find_config()
        self._tiers: dict[str, TierConfig] = {}
        self._load()

    def _find_config(self) -> Path:
        data_dir = os.environ.get("KELPMESH_STUDIO_DATA", "")
        if data_dir:
            candidate = Path(data_dir) / "pricing.yml"
            if candidate.exists():
                return candidate
        return _PACKAGE_DEFAULT

    def _load(self) -> None:
        # pricing.yml is optional — if missing, fall back to licensing.py TIER_DEFS
        # (the single source of truth for tier definitions).
        if not self._path.exists():
            from kelpmesh_studio.licensing import (
                TIER_DEFS, F_AUTH, F_RBAC, F_API_KEYS, F_GIT_SYNC,
                F_ALERTS, F_SSO, F_AUDIT_LOG, F_ADV_SCHEDULING,
            )
            for name, td in TIER_DEFS.items():
                feats = td.features
                self._tiers[name] = TierConfig(
                    name=td.label,
                    price_monthly_chf=float(td.price_usd_user_month),
                    max_users=td.max_users,
                    max_models=0,
                    max_projects=td.max_projects,
                    max_schedules_per_project=0,
                    pro_features=F_ADV_SCHEDULING in feats,
                    sso=F_SSO in feats,
                    audit_log=F_AUDIT_LOG in feats,
                    rbac=F_RBAC in feats,
                    api_keys=F_API_KEYS in feats,
                    git_sync=F_GIT_SYNC in feats,
                    alerts=F_ALERTS in feats,
                )
            return
        raw = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        for key, data in raw.get("tiers", {}).items():
            self._tiers[key] = TierConfig(
                name=data.get("name", key),
                price_monthly_chf=float(data.get("price_monthly_chf", 0)),
                max_users=data.get("max_users", 1),
                max_models=data.get("max_models", 20),
                max_projects=data.get("max_projects", 5),
                max_schedules_per_project=data.get("max_schedules_per_project", 1),
                pro_features=data.get("pro_features", False),
                sso=data.get("sso", False),
                audit_log=data.get("audit_log", False),
                rbac=data.get("rbac", False),
                api_keys=data.get("api_keys", False),
                git_sync=data.get("git_sync", False),
                alerts=data.get("alerts", False),
                support=data.get("support", "Community"),
            )

    def reload(self) -> None:
        self._tiers.clear()
        self._load()

    def get_tier(self, name: str) -> Optional[TierConfig]:
        return self._tiers.get(name)

    def all_tiers(self) -> dict[str, TierConfig]:
        return dict(self._tiers)

    # ------------------------------------------------------------------ #
    # Price resolution                                                     #
    # ------------------------------------------------------------------ #

    def resolve_price(
        self,
        tier_name: str,
        org_id: Optional[str] = None,
        session=None,
    ) -> dict:
        """Return effective price for an org, after overrides and active promos."""
        tier = self.get_tier(tier_name)
        if not tier:
            return {"error": f"Unknown tier '{tier_name}'"}

        base = tier.price_monthly_chf
        effective = base
        discount_applied: Optional[str] = None
        note = ""

        if session and org_id:
            override = session.query(OrgPricing).filter_by(org_id=org_id).first()
            if override and override.tier == tier_name:
                if override.valid_until is None or override.valid_until > datetime.now(timezone.utc).replace(tzinfo=None):
                    if override.custom_price_chf is not None:
                        effective = override.custom_price_chf
                        discount_applied = override.promo_code
                        note = override.note

        return {
            "tier": tier_name,
            "base_price_chf": base,
            "effective_price_chf": effective,
            "discount_applied": discount_applied,
            "note": note,
        }

    def apply_promo(
        self,
        code: str,
        tier_name: str,
        org_id: str,
        session,
    ) -> dict:
        """Apply a promo code to an org. Returns new effective price or error."""
        promo = session.query(PromoCode).filter_by(code=code.upper(), active=True).first()
        if not promo:
            return {"success": False, "error": "Invalid or expired promo code"}

        # Check expiry
        if promo.expires_at and promo.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
            return {"success": False, "error": "Promo code has expired"}

        # Check usage limit
        if promo.max_uses > 0 and promo.used_count >= promo.max_uses:
            return {"success": False, "error": "Promo code usage limit reached"}

        # Check applicable tiers
        if promo.applicable_tiers:
            allowed = [t.strip() for t in promo.applicable_tiers.split(",")]
            if tier_name not in allowed:
                return {"success": False, "error": f"Promo not valid for tier '{tier_name}'"}

        tier = self.get_tier(tier_name)
        if not tier:
            return {"success": False, "error": f"Unknown tier '{tier_name}'"}

        base = tier.price_monthly_chf
        if promo.discount_type == "pct":
            new_price = round(base * (1 - promo.discount_value / 100), 2)
        else:
            new_price = max(0.0, base - promo.discount_value)

        # Upsert OrgPricing
        existing = session.query(OrgPricing).filter_by(org_id=org_id).first()
        if existing:
            existing.tier = tier_name
            existing.custom_price_chf = new_price
            existing.promo_code = code.upper()
        else:
            session.add(OrgPricing(
                org_id=org_id,
                tier=tier_name,
                custom_price_chf=new_price,
                promo_code=code.upper(),
            ))

        promo.used_count += 1
        session.commit()

        return {
            "success": True,
            "code": code.upper(),
            "tier": tier_name,
            "base_price_chf": base,
            "effective_price_chf": new_price,
            "discount": f"{promo.discount_value}{'%' if promo.discount_type == 'pct' else ' CHF'}",
        }

    def create_promo(
        self,
        session,
        code: str,
        discount_type: str,
        discount_value: float,
        description: str = "",
        applicable_tiers: str = "",
        max_uses: int = 0,
        expires_at: Optional[datetime] = None,
    ) -> PromoCode:
        p = PromoCode(
            code=code.upper(),
            description=description,
            discount_type=discount_type,
            discount_value=discount_value,
            applicable_tiers=applicable_tiers,
            max_uses=max_uses,
            expires_at=expires_at,
        )
        session.add(p)
        session.commit()
        return p

    def set_org_override(
        self,
        session,
        org_id: str,
        tier: str,
        custom_price_chf: float,
        note: str = "",
        valid_until: Optional[datetime] = None,
    ) -> OrgPricing:
        existing = session.query(OrgPricing).filter_by(org_id=org_id).first()
        if existing:
            existing.tier = tier
            existing.custom_price_chf = custom_price_chf
            existing.note = note
            existing.valid_until = valid_until
        else:
            existing = OrgPricing(
                org_id=org_id,
                tier=tier,
                custom_price_chf=custom_price_chf,
                note=note,
                valid_until=valid_until,
            )
            session.add(existing)
        session.commit()
        return existing


# Module-level default engine (lazily replaced by create_app)
_engine = PricingEngine()


def create_tables(engine) -> None:
    Base.metadata.create_all(engine)
