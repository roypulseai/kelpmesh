"""Tier and pricing configuration for briq Studio."""
from dataclasses import dataclass, field


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


TIERS = {
    "free": Tier(
        name="Free",
        price_monthly_chf=0,
        max_users=1,
        max_models=20,
        max_projects=3,
        scheduling=False,
        sso=False,
        audit_log=False,
        support="Community (Discord)",
    ),
    "pro": Tier(
        name="Pro",
        price_monthly_chf=20,
        max_users=1,
        max_models=100,
        max_projects=20,
        scheduling=True,
        sso=False,
        audit_log=False,
        support="Email (48h)",
    ),
    "team": Tier(
        name="Team",
        price_monthly_chf=45,
        max_users=30,
        max_models=500,
        max_projects=100,
        scheduling=True,
        sso=True,
        audit_log=True,
        support="Email (8h)",
    ),
    "enterprise": Tier(
        name="Enterprise",
        price_monthly_chf=1800,
        max_users=999,
        max_models=9999,
        max_projects=999,
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
    return current_count <= tier.max_models
