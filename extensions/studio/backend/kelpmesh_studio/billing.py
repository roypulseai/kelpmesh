"""Tier and pricing — thin compatibility shim over pricing.py.

Legacy code that imports from billing.py continues to work; all
pricing logic now lives in kelpmesh_studio.pricing (configurable via
pricing.yml with promo codes and per-org overrides).
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Tier:
    name: str
    price_monthly_chf: int
    max_users: int
    max_models: int
    max_projects: int
    scheduling: bool
    sso: bool
    audit_log: bool
    support: str


# Legacy hardcoded tiers kept for backward compatibility with existing tests.
TIERS = {
    "free": Tier(
        name="Free",
        price_monthly_chf=0,
        max_users=1,
        max_models=20,
        max_projects=5,
        scheduling=True,
        sso=False,
        audit_log=False,
        support="Community (Discord)",
    ),
    "pro": Tier(
        name="Pro",
        price_monthly_chf=49,
        max_users=5,
        max_models=0,
        max_projects=0,
        scheduling=True,
        sso=False,
        audit_log=True,
        support="Email (48h SLA)",
    ),
    "team": Tier(
        name="Team",
        price_monthly_chf=149,
        max_users=20,
        max_models=0,
        max_projects=0,
        scheduling=True,
        sso=True,
        audit_log=True,
        support="Email (8h SLA)",
    ),
    "enterprise": Tier(
        name="Enterprise",
        price_monthly_chf=499,
        max_users=0,
        max_models=0,
        max_projects=0,
        scheduling=True,
        sso=True,
        audit_log=True,
        support="Dedicated (1h SLA)",
    ),
}


def get_tier(name: str) -> Tier | None:
    return TIERS.get(name)


def allowed_models(tier_name: str, current_count: int) -> bool:
    tier = get_tier(tier_name)
    if not tier:
        return False
    # 0 means unlimited
    if tier.max_models == 0:
        return True
    return current_count <= tier.max_models
