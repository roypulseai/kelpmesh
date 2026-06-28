"""Billing shim — delegates to kelpmesh_studio.licensing.

Legacy code that imports Tier / TIERS / get_tier / allowed_models from here
continues to work; all live logic now lives in licensing.py.
"""
from __future__ import annotations
from dataclasses import dataclass

from kelpmesh_studio.licensing import (  # noqa: F401 — re-exported
    TIER_DEFS,
    get_current_license,
    has_feature,
    within_limit,
    require_feature,
    require_min_tier,
    tier_info,
)


# ---------------------------------------------------------------------------
# Legacy Tier dataclass kept for backward compatibility with existing tests.
# ---------------------------------------------------------------------------

@dataclass
class Tier:
    name: str
    price_monthly_usd: int
    max_users: int
    max_models: int
    max_projects: int
    scheduling: bool
    sso: bool
    audit_log: bool
    support: str


def _to_legacy(td) -> Tier:
    return Tier(
        name=td.name,
        price_monthly_usd=td.price_usd_user_month,
        max_users=td.max_users,
        max_models=0,
        max_projects=td.max_projects,
        scheduling=True,
        sso=("sso" in td.features),
        audit_log=("audit_log" in td.features),
        support=td.support,
    )


TIERS: dict[str, Tier] = {name: _to_legacy(td) for name, td in TIER_DEFS.items()}


def get_tier(name: str) -> Tier | None:
    return TIERS.get(name)


def allowed_models(tier_name: str, current_count: int) -> bool:
    td = TIER_DEFS.get(tier_name)
    if not td:
        return False
    if td.max_projects == 0:   # unlimited
        return True
    return current_count <= td.max_projects
